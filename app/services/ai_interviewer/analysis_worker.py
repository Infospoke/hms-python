import threading
import time
import json
import logging
import os
from typing import Optional
from sqlmodel import Session, create_engine, select
from app.core import config as consts
from app.db.session import DATABASE_URL
from app import models
from app.utils import timezone_utils
from sqlalchemy import and_

logger = logging.getLogger(__name__)


class AnalysisWorker(threading.Thread):

    def __init__(self):
        super().__init__()
        self.daemon = True
        self.engine = create_engine(DATABASE_URL, echo=False)

    def run(self):
        logger.info("Background Analysis Worker Started (Sequential mode)")
        while True:
            try:
                with Session(self.engine) as session:
                    from app.services import db_operations

                    pending_response = db_operations.get_and_claim_pending_qna_response(
                        session
                    )
                    if pending_response:
                        response_id = pending_response.id
                        self._safe_process(response_id)
                    else:
                        time.sleep(2)
            except Exception as e:
                logger.error(f"Worker Loop Error: {e}")
                time.sleep(5)

    def _safe_process(self, response_id: int):
        try:
            self.process_response(response_id)
        except Exception as e:
            logger.error(f"Error in task for {response_id}: {e}")

    def _to_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_normalized_overall_score(self, analysis_data) -> float:
        """
        Return a 0-100 score from ai_analysis payload.
        Supports both current format (overall already 0-100) and legacy 0-10 overall.
        """
        if not isinstance(analysis_data, dict):
            return 0.0

        overall = self._to_float(analysis_data.get("overall"))
        metric_keys = [
            "domain_knowledge",
            "problem_solving",
            "job_relevance",
            "communication_clarity",
        ]
        metric_values = [
            self._to_float(analysis_data.get(key))
            for key in metric_keys
            if self._to_float(analysis_data.get(key)) is not None
        ]

        if overall is None:
            if metric_values:
                overall = (sum(metric_values) / len(metric_values)) * 10.0
            else:
                return 0.0
        elif metric_values:
            avg_10_scale = sum(metric_values) / len(metric_values)
            avg_100_scale = avg_10_scale * 10.0
            if abs(overall - avg_10_scale) < abs(overall - avg_100_scale):
                overall = avg_100_scale

        if overall < 0:
            return 0.0
        if overall > 100:
            return 100.0
        return round(overall, 1)

    def process_response(self, response_id: int):
        from app.services import db_operations
        from app.services.ai_interviewer.ai_interviewer import AIInterviewer
        from app import models
        import asyncio
        import os

        logger.info(f"Processing Response ID {response_id}...")
        try:
            with Session(self.engine) as session:
                response_obj = session.get(models.QNA_Analysis, response_id)
                if not response_obj:
                    logger.error(f"Response {response_id} not found")
                    return

                answer_text = response_obj.answer_text
                interview_analysis_id = response_obj.interview_analysis_id
                question_text = response_obj.question_text
                existing_ai_analysis = response_obj.ai_analysis

                interview_analysis = session.get(models.InterviewAnalysis, interview_analysis_id)
                interview_session_id = interview_analysis.interview_session_id if interview_analysis else str(interview_analysis_id)

            audio_report = None
            video_proctor_result = None

            if answer_text and answer_text.startswith("AUDIO_PENDING:"):
                audio_path = answer_text.split("AUDIO_PENDING:")[1]
                logger.info(
                    f"Found pending audio for response {response_id}: {audio_path}"
                )

                s3_key = audio_path
                import base64
                from app.services import minio_helper as aws_helper

                logger.info(f"[analysis_worker] Fetching audio from MinIO: {s3_key}")

                s3_result = aws_helper.get_audio_bytes_from_s3(s3_key)

                if s3_result.get("success"):
                    try:
                        if not hasattr(self, "confidence_monitor"):
                            from app.services.ai_interviewer.confidence_monitor import (
                                ConfidenceMonitor,
                            )

                            self.confidence_monitor = ConfidenceMonitor()

                        audio_bytes = s3_result["audio_bytes"]
                        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

                        audio_extension = os.path.splitext(s3_key)[1] or ".wav"

                        audio_report = asyncio.run(
                            self.confidence_monitor.generate_comprehensive_report(
                                base64_audio=audio_b64,
                                audio_extension=audio_extension,
                            )
                        )

                        aws_helper.delete_s3_object(s3_key)

                        answer_text = audio_report.get("transcript", "")
                    except Exception as e:
                        logger.error(f"Error processing audio for {response_id}: {e}")
                        with Session(self.engine) as session:
                            response_obj = session.get(models.QNA_Analysis, response_id)
                            if response_obj:
                                response_obj.answer_text = "Error in audio processing"
                                response_obj.ai_analysis = {"status": "error"}
                                session.add(response_obj)
                                session.commit()
                                self.check_interview_completion(
                                    session, response_obj.interview_analysis_id
                                )
                        return
                else:
                    logger.error(f"Audio file missing in S3: {s3_key}")
                    with Session(self.engine) as session:
                        response_obj = session.get(models.QNA_Analysis, response_id)
                        if response_obj:
                            response_obj.answer_text = "Audio file missing"
                            response_obj.ai_analysis = {"status": "error"}
                            session.add(response_obj)
                            session.commit()
                            self.check_interview_completion(
                                session, response_obj.interview_analysis_id
                            )
                    return

            elif answer_text and answer_text.startswith("VIDEO_PENDING:"):
                marker_content = answer_text.split("VIDEO_PENDING:")[1]
                parts = marker_content.split("|")
                video_s3_key = parts[0].strip()
                audio_s3_key = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None

                logger.info(
                    f"Found pending video for response {response_id}: video={video_s3_key}, audio={audio_s3_key}"
                )

                import base64
                from app.services import minio_helper as aws_helper
                import tempfile

                video_bytes = None
                if video_s3_key:
                    s3_vid_res = aws_helper.get_video_bytes_from_s3(video_s3_key)
                    if s3_vid_res.get("success"):
                        video_bytes = s3_vid_res["video_bytes"]

                if audio_s3_key:
                    s3_audio_res = aws_helper.get_audio_bytes_from_s3(audio_s3_key)
                    if s3_audio_res.get("success"):
                        audio_bytes = s3_audio_res["audio_bytes"]
                        audio_extension = os.path.splitext(audio_s3_key)[1] or ".wav"

                if not audio_bytes and video_bytes:
                    audio_bytes = video_bytes
                    audio_extension = os.path.splitext(video_s3_key)[1] or ".webm"

                if audio_bytes or video_bytes:
                    temp_video_path = None
                    try:
                        if not hasattr(self, "confidence_monitor"):
                            from app.services.ai_interviewer.confidence_monitor import (
                                ConfidenceMonitor,
                            )

                            self.confidence_monitor = ConfidenceMonitor()

                        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

                        # 1. Speech transcription & audio confidence report
                        audio_report = asyncio.run(
                            self.confidence_monitor.generate_comprehensive_report(
                                base64_audio=audio_b64,
                                audio_extension=audio_extension,
                            )
                        )

                        # 2. Video lip tracking & proctoring check
                        if video_bytes:
                            vid_ext = os.path.splitext(video_s3_key)[1] or ".webm"
                            with tempfile.NamedTemporaryFile(suffix=vid_ext, delete=False) as tf:
                                tf.write(video_bytes)
                                temp_video_path = tf.name

                            from app.services.ai_interviewer.proctoring import ProctoringEngine
                            proctor_engine = ProctoringEngine()
                            video_proctor_result = proctor_engine.analyze_video_answer(temp_video_path)
                            logger.info(
                                f"[analysis_worker] Video proctoring Q{response_id}: "
                                f"lip_ratio={video_proctor_result.get('lip_movement_ratio')}, "
                                f"face_ratio={video_proctor_result.get('face_detected_ratio')}, "
                                f"violations={video_proctor_result.get('violations')}"
                            )

                            # Log all detected video proctoring violations into tb_proctoring_logs with snapshots
                            detected_violations = video_proctor_result.get("violations", [])
                            snapshots = video_proctor_result.get("violation_snapshots", {})

                            if detected_violations:
                                with Session(self.engine) as log_session:
                                    from app.services.analyze_image_worker import _save_proctoring_violation
                                    for viol in detected_violations:
                                        try:
                                            snap = None
                                            if "Lip Movement" in viol:
                                                snap = snapshots.get("proxy_speaking")
                                            elif "Face Missing" in viol or "No Face" in viol:
                                                snap = snapshots.get("no_face")
                                            elif "Multiple People" in viol:
                                                snap = snapshots.get("multiple_people")
                                            elif "Cell Phone" in viol:
                                                snap = snapshots.get("phone")
                                            elif "Looking Away" in viol:
                                                snap = snapshots.get("looking_away")
                                            if snap is None and snapshots:
                                                snap = list(snapshots.values())[0]

                                            image_path = None
                                            if snap is not None:
                                                image_path = _save_proctoring_violation(
                                                    interview_session_id,
                                                    viol,
                                                    snap,
                                                    session=log_session,
                                                )

                                            sev = "high severity" if ("Lip Movement" in viol or "Multiple People" in viol or "Face Missing" in viol or "Cell Phone" in viol) else "medium severity"

                                            proctor_log = models.ProctoringLogs(
                                                interview_analysis_id=interview_analysis_id,
                                                event_type=models.ProctoringEventType.visual_violation,
                                                details=json.dumps([f"{viol} in Answer Recording"]),
                                                image_path=image_path,
                                                tb_severity=sev,
                                            )
                                            log_session.add(proctor_log)
                                            log_session.commit()
                                            logger.info(f"[analysis_worker] Logged proctoring violation '{viol}' for Q{response_id}")
                                        except Exception as viol_err:
                                            logger.error(f"[analysis_worker] Error logging violation '{viol}': {viol_err}")

                        # 3. Delete processed video and audio objects from MinIO
                        if video_s3_key:
                            aws_helper.delete_s3_object(video_s3_key)
                            logger.info(f"[analysis_worker] Deleted processed video from MinIO: {video_s3_key}")
                        if audio_s3_key:
                            aws_helper.delete_s3_object(audio_s3_key)
                            logger.info(f"[analysis_worker] Deleted processed audio from MinIO: {audio_s3_key}")

                        answer_text = audio_report.get("transcript", "")
                    except Exception as e:
                        logger.error(f"Error processing video media for {response_id}: {e}")
                        if video_s3_key:
                            aws_helper.delete_s3_object(video_s3_key)
                        if audio_s3_key:
                            aws_helper.delete_s3_object(audio_s3_key)

                        with Session(self.engine) as session:
                            response_obj = session.get(models.QNA_Analysis, response_id)
                            if response_obj:
                                response_obj.answer_text = "Error in video media processing"
                                response_obj.ai_analysis = {"status": "error"}
                                session.add(response_obj)
                                session.commit()
                                self.check_interview_completion(
                                    session, response_obj.interview_analysis_id
                                )
                        return
                    finally:
                        if temp_video_path and os.path.exists(temp_video_path):
                            try:
                                os.remove(temp_video_path)
                            except Exception:
                                pass
                else:
                    logger.error(f"Video media file missing in MinIO: {video_s3_key}")
                    with Session(self.engine) as session:
                        response_obj = session.get(models.QNA_Analysis, response_id)
                        if response_obj:
                            response_obj.answer_text = "Video media file missing"
                            response_obj.ai_analysis = {"status": "error"}
                            session.add(response_obj)
                            session.commit()
                            self.check_interview_completion(
                                session, response_obj.interview_analysis_id
                            )
                    return

            # --- ANSWER CLARITY & COMPLETENESS EVALUATION ---
            raw_transcript = (answer_text or "").strip()
            words = [w for w in raw_transcript.split() if len(w) > 1 or w.isalnum()]
            low_fillers = {"thank you", "thank you.", "thanks", "bye", "bye bye", "no answer", "none", "n/a", ".", "...", "okay", "yes", "no"}

            is_answered = (len(raw_transcript) >= 6 and len(words) >= 3 and raw_transcript.lower() not in low_fillers)
            is_inaudible = ("[inaudible]" in raw_transcript.lower())
            is_clear = is_answered and not is_inaudible

            if not is_answered:
                clarity_rating = "Unanswered / Silent"
                # Log unanswered warning into tb_proctoring_logs
                with Session(self.engine) as log_session:
                    try:
                        proctor_log = models.ProctoringLogs(
                            interview_analysis_id=interview_analysis_id,
                            event_type=models.ProctoringEventType.audio_violation,
                            details=json.dumps(["Question Unanswered / Silent Submission in Answer"]),
                            image_path=None,
                            tb_severity="low severity",
                        )
                        log_session.add(proctor_log)
                        log_session.commit()
                        logger.info(f"[analysis_worker] Logged unanswered violation for Q{response_id}")
                    except Exception as unans_err:
                        logger.error(f"[analysis_worker] Error logging unanswered log: {unans_err}")

                content_result = {
                    "domain_knowledge": 0,
                    "problem_solving": 0,
                    "job_relevance": 0,
                    "communication_clarity": 0,
                    "relevant_answer": "No",
                    "overall": 0.0,
                    "feedback": "Candidate did not provide an answer (Question was unanswered / silent recording).",
                    "ai_suggested_answer": "Please provide a comprehensive technical answer addressing the question.",
                }
            elif not is_clear:
                clarity_rating = "Low Audio Clarity / Inaudible"
                with Session(self.engine) as log_session:
                    try:
                        proctor_log = models.ProctoringLogs(
                            interview_analysis_id=interview_analysis_id,
                            event_type=models.ProctoringEventType.audio_violation,
                            details=json.dumps(["Low Audio Clarity / Inaudible Speech in Answer"]),
                            image_path=None,
                            tb_severity="low severity",
                        )
                        log_session.add(proctor_log)
                        log_session.commit()
                    except Exception as inaud_err:
                        logger.error(f"[analysis_worker] Error logging low clarity log: {inaud_err}")

                with Session(self.engine) as session:
                    context = db_operations.get_interview_context(
                        session, interview_analysis_id
                    )
                interviewer = AIInterviewer(
                    job_role=context["job_title"] if context else "Candidate",
                    job_description=context["job_description"] if context else "",
                    experience=context["experience_level"] if context else "",
                    skills=context["skills"] if context else "",
                    topics=context["tb_interview_focus_areas"] if context else [""],
                    resume_text=context["resume_text"] if context else "",
                )
                content_result = interviewer.analyze_answer(question_text, answer_text)
            else:
                clarity_rating = "Clear"
                with Session(self.engine) as session:
                    context = db_operations.get_interview_context(
                        session, interview_analysis_id
                    )
                interviewer = AIInterviewer(
                    job_role=context["job_title"] if context else "Candidate",
                    job_description=context["job_description"] if context else "",
                    experience=context["experience_level"] if context else "",
                    skills=context["skills"] if context else "",
                    topics=context["tb_interview_focus_areas"] if context else [""],
                    resume_text=context["resume_text"] if context else "",
                )
                content_result = interviewer.analyze_answer(question_text, answer_text)

            if content_result:
                final_analysis = content_result
                if audio_report:
                    final_analysis.update(audio_report)
                elif existing_ai_analysis and isinstance(existing_ai_analysis, dict):
                    blocked_keys = {
                        "status",
                        "overall",
                        "domain_knowledge",
                        "problem_solving",
                        "job_relevance",
                        "communication_clarity",
                        "relevant_answer",
                        "feedback",
                    }
                    for key, value in existing_ai_analysis.items():
                        if key not in blocked_keys:
                            final_analysis[key] = value

                # Attach answer quality and proctoring violation summary
                final_analysis["answer_quality"] = {
                    "is_answered": is_answered,
                    "is_clear": is_clear,
                    "clarity_rating": clarity_rating,
                    "transcript": raw_transcript,
                    "proctoring_violations": video_proctor_result.get("violations", []) if video_proctor_result else [],
                }

                metrics = []
                for key in [
                    "domain_knowledge",
                    "problem_solving",
                    "job_relevance",
                    "communication_clarity",
                ]:
                    if key in final_analysis:
                        metrics.append(final_analysis[key])

                if metrics and is_answered:
                    final_analysis["overall"] = round(
                        (sum(metrics) / len(metrics)) * 10, 1
                    )
                elif not is_answered:
                    final_analysis["overall"] = 0.0

                with Session(self.engine) as session:
                    response_obj = session.get(models.QNA_Analysis, response_id)
                    if response_obj:
                        response_obj.answer_text = answer_text
                        response_obj.ai_analysis = final_analysis
                        session.add(response_obj)
                        session.commit()
                        logger.info(
                            f"Full analysis saved for response ID {response_id} (Status: {clarity_rating})"
                        )
                        self.check_interview_completion(session, interview_analysis_id)
            else:
                logger.warning(
                    f"AI analysis returned no result for content analysis of {response_id}"
                )
                with Session(self.engine) as error_session:
                    response_obj = error_session.get(models.QNA_Analysis, response_id)
                    if response_obj:
                        response_obj.ai_analysis = {
                            "status": "error",
                            "message": "AI analysis returned no result",
                        }
                        error_session.add(response_obj)
                        error_session.commit()
                        self.check_interview_completion(
                            error_session, response_obj.interview_analysis_id
                        )
        except Exception as e:
            logger.error(f"Error processing response {response_id}: {e}")
            try:
                with Session(self.engine) as error_session:
                    response_obj = error_session.get(models.QNA_Analysis, response_id)
                    if response_obj:
                        response_obj.ai_analysis = {
                            "status": "error",
                            "message": str(e),
                        }
                        error_session.add(response_obj)
                        error_session.commit()
                        self.check_interview_completion(
                            error_session, response_obj.interview_analysis_id
                        )
            except Exception as inner_e:
                logger.error(
                    f"Failed to log error for response {response_id}: {inner_e}"
                )

    def check_interview_completion(self, session: Session, interview_analysis_id: int):
        from app.services import db_operations
        from app import models
        from sqlmodel import select

        try:
            interview_analysis = session.exec(
                select(models.InterviewAnalysis).where(
                    models.InterviewAnalysis.id == interview_analysis_id
                )
            ).first()
            if not interview_analysis:
                return
            if interview_analysis.status != models.StatusEnum.completed:
                return
            pending_count = db_operations.get_pending_qna_count(
                session, interview_analysis_id
            )
            if pending_count == 0:
                logger.info(
                    f"All responses analyzed for interview analysis ID {interview_analysis_id}, starting finalization"
                )
                self.finalize_interview(session, interview_analysis)
        except Exception as e:
            logger.error(f"Error checking interview completion: {e}")

    def finalize_interview(
        self, session: Session, interview_analysis: models.InterviewAnalysis
    ):
        from app.services import db_operations
        from sqlmodel import select
        from app import models

        try:
            all_responses = session.exec(
                select(models.QNA_Analysis).where(
                    models.QNA_Analysis.interview_analysis_id == interview_analysis.id
                )
            ).all()
            if not all_responses:
                interview_analysis.total_score = 0.0
                interview_analysis.recommendation = "REJECT"
                session.add(interview_analysis)
                session.commit()
                return

            total_score_sum = 0
            for resp in all_responses:
                if resp.ai_analysis:
                    try:
                        data = (
                            resp.ai_analysis
                            if isinstance(resp.ai_analysis, dict)
                            else json.loads(resp.ai_analysis)
                        )
                        score = self._extract_normalized_overall_score(data)
                        total_score_sum += score
                    except Exception as e:
                        logger.warning(
                            f"Could not parse analysis for response {resp.id}: {e}"
                        )

            count = len(all_responses)
            interview_analysis.total_score = round(total_score_sum / count, 1)
            if interview_analysis.total_score >= 85.0:
                interview_analysis.recommendation = "STRONG HIRE"
            elif interview_analysis.total_score >= 70.0:
                interview_analysis.recommendation = "HIRE"
            elif interview_analysis.total_score >= 40.0:
                interview_analysis.recommendation = "CONSIDER"
            else:
                interview_analysis.recommendation = "REJECT"

            interview_analysis.analysis_completed = True
            interview_analysis.interview_analysis_date = timezone_utils.get_ist_now()

            candidate_name = db_operations.get_candidate_name(
                session, interview_analysis.application_id
            )

            job_title = ""
            job_details_row = None
            try:
                job_id = interview_analysis.job_id
                job_details_row = session.exec(
                    select(models.CreateJobDetails).where(                        
                        models.CreateJobDetails.job_id == job_id
                    )
                ).first()
                if job_details_row and job_details_row.job_title:
                    job_title = job_details_row.job_title
            except Exception as e:
                logger.error(f"Error fetching job details for activity feed: {e}")

            activity_message = f"AI interview completed for {candidate_name}"
            if job_title:
                activity_message += f" for {job_title}"

            activity_feed = models.ActivityFeed(
                timestamp=timezone_utils.get_ist_now(),
                activity=activity_message,
            )
            session.add(activity_feed)

            try:
                if job_details_row and job_details_row.plan_id is not None:
                    plan_id = job_details_row.plan_id

                    all_plan_rounds = []
                    
                    all_plan_rounds_rows = session.exec(
                        select(models.InterviewRound)
                        .where(models.InterviewRound.interview_plan_id == plan_id)
                        .order_by(models.InterviewRound.round_order.asc())
                    ).all()
                    
                    for row in all_plan_rounds_rows:

                        stage_val = row.stage_type_id
                        
                        all_plan_rounds.append({
                            "id": row.id,
                            "round_order": row.round_order,
                            "stage_name": row.stage_name,
                            "stage_type": row.stage_type,
                            "stage_type_id": stage_val,
                            "interview_plan_id": row.interview_plan_id
                        })
                    
                    # Find the AI Interview round dynamically (robust check matching stage_type or stage_name)
                    ai_round = None
                    for r in all_plan_rounds:
                        s_name = str(r.get("stage_name") or "").lower().replace(" ", "").replace("_", "")
                        s_type = str(r.get("stage_type") or "").lower().replace(" ", "").replace("_", "")
                        if "aiinterview" in s_name or "aiinterview" in s_type:
                            ai_round = r
                            break

                    # Fallback to the first round in the plan if no AI round is found by name/type
                    if not ai_round and all_plan_rounds:
                        # ai_round = all_plan_rounds[0]
                        logger.error(f"No AI round found in the interview plan {plan_id=}")
                        return

                    if ai_round:
                        row_order = ai_round.get("round_order")

                        # Query the next round in the plan
                        next_interview_round = session.exec(
                            select(models.InterviewRound).where(
                                models.InterviewRound.interview_plan_id == plan_id,
                                models.InterviewRound.round_order == row_order + 1
                            )
                        ).first()

                        stage_id = None
                        interviewer_id = None
                        print(f"{next_interview_round=}")
                        if next_interview_round:
                            # Query the assignment for the next round
                            from sqlalchemy import and_
                            target_assignment = session.exec(
                                select(models.InterviewAssignment).where(
                                    and_(
                                        models.InterviewAssignment.job_id == job_id,
                                        models.InterviewAssignment.plan_id == plan_id,
                                        models.InterviewAssignment.stage_type_id == next_interview_round.stage_type_id
                                    )
                                )
                            ).first()

                            if target_assignment:
                                print(f"{target_assignment=}")
                                if target_assignment.status and target_assignment.status.lower() == "accepted":
                                    stage_id = next_interview_round.stage_type_id
                                    interviewer_id = target_assignment.interviewer_user_id or target_assignment.user_id
                                else:
                                    # Fallback/default if status is not accepted (or we still want stage_id anyway)
                                    stage_id = next_interview_round.stage_type_id
                                    interviewer_id = target_assignment.interviewer_user_id or target_assignment.user_id
                            else:
                                # Fallback if no target assignment is found for that stage
                                stage_id = next_interview_round.stage_type_id

                        if stage_id is not None:
                            current_stage = session.exec(
                                select(models.InterviewCurrentStage).where(
                                    models.InterviewCurrentStage.application_id == interview_analysis.application_id
                                )
                            ).first()
                            
                            if not current_stage:
                                current_stage = models.InterviewCurrentStage(
                                    application_id=interview_analysis.application_id
                                )
                                logger.info(f"Creating new InterviewCurrentStage record for application {interview_analysis.application_id}")
                            
                            current_stage.current_stage_type = stage_id
                            current_stage.round_order = next_interview_round.round_order if next_interview_round else row_order
                            current_stage.to_schedule = False
                            current_stage.interviewer_id = interviewer_id
                            
                            current_stage.interview_completed = False
                            current_stage.interview_completed_on = timezone_utils.get_ist_now()
                            current_stage.feedback_status = "pending"
                            
                            logger.info(
                                f"Updating candidate {interview_analysis.application_id} current stage to next round stage {stage_id} "
                                f"(round_order: {current_stage.round_order}, to_schedule: False, interviewer: {interviewer_id})"
                            )
                            session.add(current_stage)
                        else:
                            logger.warning(f"No stage_type_id found for plan_id {plan_id} and target round {ai_round.get('stage_name')}")
                else:
                    logger.warning(f"No plan_id found in tb_create_job_details for job_id {job_id}")
            except Exception as db_err:
                logger.error(f"Error updating current stage records: {db_err}", exc_info=True)

            session.add(interview_analysis)
            session.commit()
            logger.info(
                f"Interview {interview_analysis.id} finalized with total score: {interview_analysis.total_score}"
            )
        except Exception as e:
            logger.error(f"Error finalizing interview: {e}")
            session.rollback()
