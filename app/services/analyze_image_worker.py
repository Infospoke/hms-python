import base64
import logging
import time
from json import dumps as json_dumps

import cv2
import numpy as np
from sqlmodel import Session, select

from app.db.session import engine
from app import models

from app.services import kafka_helper
from app.services import minio_helper as aws_helper
from app.utils import timezone_utils

logger = logging.getLogger(__name__)

_proctoring_engine = None


def _get_proctoring_engine():
    global _proctoring_engine
    if _proctoring_engine is None:
        from app.services.ai_interviewer.proctoring import ProctoringEngine

        _proctoring_engine = ProctoringEngine()
    return _proctoring_engine


def _save_proctoring_violation(
    interview_session_id: str, alert_type: str, image
) -> str:
    timestamp_str = timezone_utils.get_ist_now().strftime("%Y%m%d_%H%M%S_%f")
    clean_alert_type = alert_type.replace(" ", "_").lower()
    image_filename = f"violation_{clean_alert_type}_{timestamp_str}.jpg"
    s3_object_name = f"ai-interviews/proctoring/{interview_session_id}/{image_filename}"

    _, buffer = cv2.imencode(".jpg", image)
    image_bytes = buffer.tobytes()

    upload_result = aws_helper.upload_image_to_s3(image_bytes, s3_object_name)
    if upload_result.get("success"):
        return upload_result.get("s3_url")
    raise Exception(f"S3 upload failed: {upload_result.get('error')}")


def _process_message(payload: dict) -> None:
    interview_session_id = payload.get("interview_session_id")
    image_base64 = payload.get("image_base64", "")
    try:
        if image_base64.startswith("data:image"):
            _, image_base64 = image_base64.split(",", 1)
        image_data = base64.b64decode(image_base64)

        image_array = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.error(
            f"Worker: failed to decode/fetch image for session {interview_session_id}: {e}"
        )
        return

    engine_instance = _get_proctoring_engine()
    result = engine_instance.analyze_frame(image)

    if result.get("alerts"):
        with Session(engine) as session:
            interview_analysis = session.exec(
                select(models.InterviewAnalysis).where(
                    models.InterviewAnalysis.interview_session_id
                    == interview_session_id
                )
            ).first()

            if not interview_analysis:
                logger.warning(
                    f"Worker: InterviewAnalysis not found for session {interview_session_id}"
                )
                return

            try:
                image_path = _save_proctoring_violation(
                    interview_session_id, result["alerts"][0], image
                )

                proctoring_log = models.ProctoringLogs(
                    interview_analysis_id=interview_analysis.id,
                    event_type=models.ProctoringEventType.visual_violation,
                    details=json_dumps(result["alerts"]),
                    image_path=image_path,
                )
                session.flush()
                session.add(proctoring_log)
                session.commit()
                # logger.info(
                #     f"Worker: proctoring violation logged for session {interview_session_id}"
                # )
            except Exception as err:
                logger.error(f"Worker: failed to log proctoring violation: {err}")
    else:
        logger.debug(
            f"Worker: no alerts for session {interview_session_id}, metrics={result.get('metrics')}"
        )


from concurrent.futures import ThreadPoolExecutor
import json
from confluent_kafka import KafkaError

executor = ThreadPoolExecutor(max_workers=10)


def _safe_process_message(body: dict) -> None:
    try:
        _process_message(body)
    except Exception as e:
        logger.error(f"Worker: unhandled error in parallel processor: {e}")


def run_worker() -> None:
    logger.info(
        "analyze_image_worker: started, polling Kafka topic... (Parallel mode)"
    )
    consumer = kafka_helper.get_kafka_consumer()
    consumer.subscribe([kafka_helper.KAFKA_TOPIC])

    while True:
        try:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    time.sleep(1)
                    continue
                logger.error(f"Worker: Kafka error: {msg.error()}")
                continue

            try:
                body_str = msg.value().decode("utf-8")
                body = json.loads(body_str)
                executor.submit(_safe_process_message, body)
            except Exception as e:
                logger.error(f"Worker: error dispatching message: {e}")
            finally:
                consumer.commit(msg, asynchronous=True)
        except Exception as e:
            logger.error(f"Worker: polling error: {e}")
            time.sleep(5)


# from concurrent.futures import ThreadPoolExecutor
#
# executor = ThreadPoolExecutor(max_workers=8)
#
#
# def run_worker() -> None:
#     import json
#     from confluent_kafka import KafkaError
#
#     logger.info("analyze_image_worker: started, polling Kafka topic... (Parallel mode)")
#     consumer = kafka_helper.get_kafka_consumer()
#     consumer.subscribe([kafka_helper.KAFKA_TOPIC])
#
#     while True:
#         try:
#             msg = consumer.poll(timeout=1.0)
#             if msg is None:
#                 continue
#             if msg.error():
#                 if msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
#                     time.sleep(1)
#                     continue
#                 logger.error(f"Worker: Kafka error: {msg.error()}")
#                 continue
#
#             try:
#                 body_str = msg.value().decode("utf-8")
#                 body = json.loads(body_str)
#
#                 # Dispatch processing to the thread pool
#                 executor.submit(_safe_process_message, body)
#
#             except Exception as e:
#                 logger.error(f"Worker: error dispatching message: {e}")
#             finally:
#                 # We commit immediately after dispatching or we'd have to wait for the thread
#                 # This is okay if we assume the thread pool is reliable
#                 consumer.commit(msg, asynchronous=True)
#         except Exception as e:
#             logger.error(f"Worker: polling error: {e}")
#             time.sleep(5)
#
#
# def _safe_process_message(body):
#     try:
#         _process_message(body)
#     except Exception as e:
#         logger.error(f"Worker: unhandled error in parallel processor: {e}")
