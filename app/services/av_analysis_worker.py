"""Worker that analyses recorded answer clips for audio/visual proctoring.

Runs on its own Kafka topic and its own consumer group, separate from
`analyze_image_worker`, so a backlog of slow clip jobs can never delay live
per-frame image proctoring.

Retention: a clip judged `clean` is deleted from MinIO immediately after
analysis, which is the point of analysing it at all. Clips that are
`suspicious` are kept as the evidence a human would need to adjudicate, and
`not_measurable` clips are kept by default because they are the only way to
find out why analysis failed. Both are configurable. The metrics row is
written either way, so thresholds stay tunable even once the media is gone.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from confluent_kafka import KafkaError
from sqlmodel import Session, select

from app import models
from app.core import config as consts
from app.db.session import engine
from app.services import kafka_helper
from app.services import minio_helper as aws_helper

logger = logging.getLogger(__name__)

_analyzer = None

# Clip analysis is heavy (ffmpeg demux + per-frame FaceMesh over a whole
# answer), so concurrency is deliberately far lower than the image worker's.
executor = ThreadPoolExecutor(max_workers=2)


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from app.services.ai_interviewer.av_analysis import AVAnswerAnalyzer

        _analyzer = AVAnswerAnalyzer()
    return _analyzer


def _should_retain(verdict: str) -> bool:
    if verdict == models.AVVerdictEnum.suspicious:
        return consts.AV_KEEP_SUSPICIOUS_CLIPS
    if verdict == models.AVVerdictEnum.not_measurable:
        return consts.AV_KEEP_NOT_MEASURABLE_CLIPS
    if verdict == models.AVVerdictEnum.error:
        # Keep the media when analysis itself broke, otherwise the failure can
        # never be reproduced.
        return consts.AV_KEEP_ERROR_CLIPS
    return False


def _store_result(payload: dict, result: dict, clip_key: str) -> None:
    session_id = payload["interview_session_id"]
    question_index = payload.get("question_index")
    verdict = result.get("verdict", models.AVVerdictEnum.error)

    with Session(engine) as session:
        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                models.InterviewAnalysis.interview_session_id == session_id
            )
        ).first()

        if not interview_analysis:
            logger.warning(
                f"AV worker: InterviewAnalysis not found for session {session_id}; "
                "dropping clip to avoid orphaned media"
            )
            aws_helper.delete_s3_object(clip_key)
            return

        retain = _should_retain(verdict)
        if not retain:
            delete_result = aws_helper.delete_s3_object(clip_key)
            if not delete_result.get("success"):
                # The row must reflect what is actually in MinIO, so a failed
                # delete is recorded as retained rather than silently lost.
                logger.error(
                    f"AV worker: failed to delete clean clip {clip_key}: "
                    f"{delete_result.get('error')}"
                )
                retain = True

        row = models.AnswerAVAnalysis(
            interview_analysis_id=interview_analysis.id,
            interview_session_id=session_id,
            question_index=question_index,
            clip_path=clip_key if retain else None,
            clip_retained=retain,
            verdict=verdict,
            reasons=result.get("reasons", []),
            duration_sec=result.get("duration_sec", 0.0),
            video_fps=result.get("video_fps", 0.0),
            frame_count=result.get("frame_count", 0),
            frames_with_face=result.get("frames_with_face", 0),
            face_coverage=result.get("face_coverage", 0.0),
            speech_seconds=result.get("speech_seconds", 0.0),
            speech_ratio=result.get("speech_ratio", 0.0),
            distinct_voice_clusters=result.get("distinct_voice_clusters", 0),
            mouth_active_ratio_during_speech=result.get(
                "mouth_active_ratio_during_speech", 0.0
            ),
            mouth_active_ratio_during_silence=result.get(
                "mouth_active_ratio_during_silence", 0.0
            ),
            mouth_active_ratio_overall=result.get("mouth_active_ratio_overall", 0.0),
            metrics=result.get("metrics"),
        )
        session.add(row)

        if verdict == models.AVVerdictEnum.suspicious and not consts.AV_SHADOW_MODE:
            _log_violations(session, interview_analysis.id, question_index, result,
                            clip_key if retain else None)

        session.commit()

    logger.info(
        f"AV worker: session {session_id} Q{question_index} -> {verdict} "
        f"(speech {result.get('speech_seconds')}s, "
        f"mouth-active-during-speech {result.get('mouth_active_ratio_during_speech')}, "
        f"voices {result.get('distinct_voice_clusters')}, clip_retained={retain})"
    )


def _log_violations(session, interview_analysis_id, question_index, result, clip_key):
    """Write one ProctoringLogs row per distinct signal that fired.

    Severity is intentionally "medium severity" rather than high: neither
    signal is calibrated, and both have benign explanations. These rows are
    evidence for a recruiter to review, not a finding.
    """
    reasons = result.get("reasons", [])
    mouth_reasons = [r for r in reasons if "mouth moved" in r]
    voice_reasons = [r for r in reasons if "voice clusters" in r]

    for event_type, matched in (
        (models.ProctoringEventType.av_mouth_mismatch, mouth_reasons),
        (models.ProctoringEventType.multiple_voices, voice_reasons),
    ):
        if not matched:
            continue
        session.add(
            models.ProctoringLogs(
                interview_analysis_id=interview_analysis_id,
                event_type=event_type,
                details=json.dumps(
                    {
                        "question_index": question_index,
                        "reasons": matched,
                        "speech_seconds": result.get("speech_seconds"),
                        "mouth_active_ratio_during_speech": result.get(
                            "mouth_active_ratio_during_speech"
                        ),
                        "distinct_voice_clusters": result.get(
                            "distinct_voice_clusters"
                        ),
                        "requires_human_review": True,
                    }
                ),
                image_path=clip_key,
                tb_severity="Medium severity",
            )
        )


def _process_message(payload: dict) -> None:
    session_id = payload.get("interview_session_id")
    clip_key = payload.get("clip_key")
    extension = payload.get("extension", ".webm")

    if not session_id or not clip_key:
        logger.error(f"AV worker: malformed payload, dropping: {payload}")
        return

    fetched = aws_helper.get_object_bytes(clip_key)
    if not fetched.get("success"):
        logger.error(
            f"AV worker: could not fetch clip {clip_key}: {fetched.get('error')}"
        )
        return

    try:
        result = _get_analyzer().analyze(fetched["content"], extension=extension)
    except Exception as e:
        logger.error(f"AV worker: analysis failed for {clip_key}: {e}", exc_info=True)
        result = {
            "verdict": models.AVVerdictEnum.error,
            "reasons": [f"analysis failed: {e}"],
            "metrics": {"error": str(e)},
        }

    _store_result(payload, result, clip_key)


def _safe_process_message(payload: dict) -> None:
    try:
        _process_message(payload)
    except Exception as e:
        logger.error(f"AV worker: unhandled error: {e}", exc_info=True)


def run_worker() -> None:
    topic = kafka_helper.get_av_topic()
    logger.info(f"av_analysis_worker: started, polling Kafka topic '{topic}'...")

    consumer = kafka_helper.get_kafka_consumer(
        topic=topic,
        # Distinct group so offsets never collide with the image worker's.
        group_id=f"{consts.KAFKA_GROUP_ID or 'hms'}-av-analysis",
    )
    consumer.subscribe([topic])

    while True:
        try:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    time.sleep(1)
                    continue
                logger.error(f"AV worker: Kafka error: {msg.error()}")
                continue

            try:
                payload = json.loads(msg.value().decode("utf-8"))
                executor.submit(_safe_process_message, payload)
            except Exception as e:
                logger.error(f"AV worker: error dispatching message: {e}")
            finally:
                consumer.commit(msg, asynchronous=True)
        except Exception as e:
            logger.error(f"AV worker: polling error: {e}")
            time.sleep(5)
