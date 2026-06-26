from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select
from app import models
from app.api import deps
from app.schemas import *
from app.core import config as consts
from uuid import uuid4
from app.services.email import interview_emails
from app.services.ai_interviewer.ai_interviewer import AIInterviewer
from app.services.live_stream_manager import stream_manager
from app.utils import utils
from app.utils import timezone_utils
from app.services.resume_parser.s3_resume_parser import S3ResumeParser
from app.services.seb.seb_verify import verify_seb
from app.services import db_operations
from app.services import minio_helper as aws_helper
import base64
import logging
import numpy as np
import cv2
from json import dumps as json_dumps
from pathlib import Path
from app.utils import timezone_utils
from sqlalchemy import and_
import pytz
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/create-interview-session")
def create_interview_session(
    data: CreateInterviewSessionRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    interview_session = session.exec(
        select(models.InterviewSessions).where(
            models.InterviewSessions.application_id == data.application_id
        )
    ).first()

    if interview_session is not None:
        return {
            "success": True,
            "application_id": interview_session.application_id,
            "interview_session_id": interview_session.interview_session_id,
            "message": "Interview Session already exists for candidate."
        }

    try:
        from sqlalchemy import inspect, text
        from app.db.session import engine

        inspector = inspect(engine)
        columns = [
            c["name"]
            for c in inspector.get_columns(models.InterviewSessions.__tablename__)
        ]
        if "question_type" not in columns:
            logger.info(
                f"Patching {models.InterviewSessions.__tablename__} table: adding question_type column"
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN question_type VARCHAR(20) DEFAULT 'AI'"
                )
            )
            session.commit()

        if "scheduled_time" not in columns:
            logger.info(
                f"Patching {models.InterviewSessions.__tablename__} table: adding scheduling columns"
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN scheduled_time TIMESTAMP NULL"
                )
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN is_scheduled BOOLEAN DEFAULT FALSE"
                )
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN schedule_email_sent BOOLEAN DEFAULT FALSE"
                )
            )
            session.commit()

        if "status" not in columns:
            logger.info(
                f"Patching {models.InterviewSessions.__tablename__} table: adding status column"
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN status VARCHAR(20) DEFAULT 'Scheduled'"
                )
            )
            session.commit()

        if "interview_analysis_date" not in [
            c["name"]
            for c in inspector.get_columns(models.InterviewAnalysis.__tablename__)
        ]:
            logger.info(
                f"Patching {models.InterviewAnalysis.__tablename__} table: adding interview_analysis_date column"
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewAnalysis.__tablename__} ADD COLUMN interview_analysis_date TIMESTAMP DEFAULT NULL"
                )
            )
            session.commit()

        if "interview_scheduled_datetime" not in columns:
            logger.info(
                f"Patching {models.InterviewSessions.__tablename__} table: adding interview_scheduled_datetime column"
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN interview_scheduled_datetime TIMESTAMP NULL"
                )
            )
            session.commit()


        analysis_columns = [
            c["name"]
            for c in inspector.get_columns(models.InterviewAnalysis.__tablename__)
        ]
        if "interview_started_datetime" not in analysis_columns:
            logger.info(
                f"Patching {models.InterviewAnalysis.__tablename__} table: adding interview_started_datetime column"
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewAnalysis.__tablename__} ADD COLUMN interview_started_datetime TIMESTAMP NULL"
                )
            )
            session.commit()

        session.commit()

        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == data.application_id
            )
        ).first()

        interview_session_id = uuid4()

        interview_session = models.InterviewSessions(
            interview_session_id=str(interview_session_id),
            application_id=data.application_id,
            question_type=data.question_type,
            exam_exit_password="",
            status=None,
        )

        interview_analysis = models.InterviewAnalysis(
            application_id=interview_session.application_id,
            interview_session_id=interview_session.interview_session_id,
            status=models.StatusEnum.not_started,
            questions=[],
            job_id=job_application.job_id,
        )

        session.add(interview_session)
        session.flush()
        session.add(interview_analysis)
        session.commit()
        session.refresh(interview_session)
        session.refresh(interview_analysis)

        interview_emails.send_interview_invitation(
            interview_session,
            background_tasks,
            session,
        )
        # Update JobApplications stage to INTERVIEW
        job_app = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == data.application_id
            )
        ).first()
        if job_app:
            job_app.current_stage = "INTERVIEW"
            job_app.stage_entry_date = timezone_utils.get_ist_now()
            session.add(job_app)
            session.commit()


        return {
            "success": True,
            "application_id": interview_session.application_id,
            "interview_session_id": interview_session.interview_session_id,
        }

    except Exception as err:
        logger.error(f"Error creating interview session: {err}")
        return {"success": False, "error": "An internal server error occurred."}


from app.services.email.interview_emails import send_interview_result_email


@router.get("/available-slots")
def get_available_slots(
    interview_session_id: str = Query(...),
    session: Session = Depends(deps.get_session),
):
    logger.info(f"get-available-slots for session {interview_session_id}")

    interview_session = session.exec(
        select(models.InterviewSessions).where(
            models.InterviewSessions.interview_session_id == interview_session_id,
            models.InterviewSessions.is_deleted == False,
        )
    ).first()

    if not interview_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active Interview Session not found",
        )

    if interview_session.is_scheduled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already scheduled.",
        )

    IST = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(IST)

    slots = []

    for day_offset in range(8):
        current_day = now_ist.date() + timedelta(days=day_offset)
        for hour in range(9, 18):
            for minute in (0, 30):
                t = datetime.min.time()
                slot_time = t.replace(hour=hour, minute=minute)
                slot_dt = datetime.combine(current_day, slot_time)
                slot_dt_aware = IST.localize(slot_dt)
                if slot_dt_aware > now_ist:
                    slots.append(slot_dt_aware.isoformat())

    return {"success": True, "available_slots": slots}


@router.post("/schedule")
def schedule_interview(
    data: ScheduleInterviewRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    logger.info(f"schedule-interview for session {data.interview_session_id}")

    interview_session = session.exec(
        select(models.InterviewSessions).where(
            models.InterviewSessions.interview_session_id == data.interview_session_id,
            models.InterviewSessions.is_deleted == False,
        )
    ).first()

    if not interview_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active Interview Session not found",
        )

    if interview_session.is_scheduled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Interview is already scheduled.",
        )

    try:
        # Combine date and time strings into a single datetime object
        dt_str = f"{data.scheduled_date} {data.scheduled_time}"
        slot_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

        IST = pytz.timezone("Asia/Kolkata")
        # Ensure the datetime corresponds to IST if needed, but typically we store naive and interpret as IST in worker

        interview_session.scheduled_time = slot_dt
        interview_session.is_scheduled = True
        interview_session.schedule_email_sent = False  # Ensure worker picks it up
        interview_session.status = models.InterviewSessionStatusEnum.upcoming
        interview_session.interview_scheduled_datetime = timezone_utils.get_ist_now()
        interview_session.scheduled_by = "applicant"

        session.add(interview_session)
        session.commit()
        session.refresh(interview_session)

        interview_emails.send_schedule_confirmation_email(
            interview_session, background_tasks, session
        )


        return {
            "success": True,
            "message": f"Interview successfully scheduled for {data.scheduled_date} at {data.scheduled_time} IST. Link will be sent 30 minutes before the interview.",
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date or time format. Use YYYY-MM-DD and HH:MM.",
        )


@router.post("/admin-schedule-interview")
def admin_schedule_interview(
    data: AdminScheduleInterviewRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    logger.info(f"admin-schedule-interview for application_id {data.application_id}")

    try:
        # --- Ensure scheduling columns exist ---
        from sqlalchemy import inspect, text
        from app.db.session import engine

        inspector = inspect(engine)
        session_columns = [
            c["name"]
            for c in inspector.get_columns(models.InterviewSessions.__tablename__)
        ]

        if "question_type" not in session_columns:
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN question_type VARCHAR(20) DEFAULT 'AI'"
                )
            )
            session.commit()

        if "scheduled_time" not in session_columns:
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN scheduled_time TIMESTAMP NULL"
                )
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN is_scheduled BOOLEAN DEFAULT FALSE"
                )
            )
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN schedule_email_sent BOOLEAN DEFAULT FALSE"
                )
            )
            session.commit()

        analysis_columns = [
            c["name"]
            for c in inspector.get_columns(models.InterviewAnalysis.__tablename__)
        ]
        if "final_decision" not in analysis_columns:
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewAnalysis.__tablename__} ADD COLUMN final_decision VARCHAR(20) DEFAULT ''"
                )
            )
            session.commit()
        else:
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewAnalysis.__tablename__} ALTER COLUMN final_decision DROP NOT NULL"
                )
            )
            session.commit()

        if "interview_scheduled_datetime" not in session_columns:
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewSessions.__tablename__} ADD COLUMN interview_scheduled_datetime TIMESTAMP NULL"
                )
            )
            session.commit()


        if "interview_started_datetime" not in analysis_columns:
            session.execute(
                text(
                    f"ALTER TABLE {models.InterviewAnalysis.__tablename__} ADD COLUMN interview_started_datetime TIMESTAMP NULL"
                )
            )
            session.commit()

        # --- Look up (or auto-create) the interview session ---
        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id == data.application_id,
                models.InterviewSessions.is_deleted == False,
            )
        ).first()

        # --- Schedule the interview ---
        dt_str = f"{data.scheduled_date} {data.scheduled_time}"
        slot_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

        interview_session.scheduled_time = slot_dt
        interview_session.is_scheduled = True
        interview_session.schedule_email_sent = False
        interview_session.status = models.InterviewSessionStatusEnum.upcoming
        interview_session.interview_scheduled_datetime = timezone_utils.get_ist_now()
        interview_session.scheduled_by = "recruiter"
        
        session.add(interview_session)
        session.commit()
        session.refresh(interview_session)

        # --- Send schedule confirmation email only ---
        interview_emails.send_schedule_confirmation_email(
            interview_session, background_tasks, session
        )

        # Update JobApplications stage to INTERVIEW
        job_app = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == data.application_id
            )
        ).first()
        if job_app:
            job_app.current_stage = "INTERVIEW"
            job_app.stage_entry_date = timezone_utils.get_ist_now()
            session.add(job_app)
            session.commit()

        return {
            "success": True,
            "message": (
                f"Interview successfully scheduled for {data.scheduled_date} at "
                f"{data.scheduled_time} IST. A confirmation email has been sent to the candidate. "
                f"The interview link will be sent 30 minutes before the interview."
            ),
            "interview_session_id": interview_session.interview_session_id,
        }

    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date or time format. Use YYYY-MM-DD and HH:MM.",
        )
    except Exception as err:
        logger.error(f"Error in admin-schedule-interview: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while scheduling the interview.",
        )


@router.post("/update-final-candidate-decision")
def update_final_candidate_decision(
    data: UpdateFinalDecisionRequest,
    session: Session = Depends(deps.get_session),
):
    logger.info(
        f"update-final-decision for application_id {data.application_id} to {data.decision}"
    )

    if data.decision not in ["HIRED", "REJECTED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid decision. Use 'HIRED' or 'REJECTED'.",
        )

    try:
        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == data.application_id
            )
        ).first()

        job = session.exec(
            select(models.Jobs).where(models.Jobs.job_id == job_application.job_id)
        ).first()

        comment = data.comment or ""
        resolved_status = "Joined" if data.decision == "HIRED" else "Rejected"

        candidate_info = models.CandidateInfo(
            application_id=data.application_id,
            status=resolved_status,
            comment=comment,
            updated_date=timezone_utils.get_ist_now(),
            first_name=job_application.first_name,
            last_name=job_application.last_name,
            phone_number=job_application.ph_no,
            email=job_application.email,
            job_country=job.job_country if job else None,
            job_title=job.job_title if job else None,
            job_id=job_application.job_id,
        )

        # Update JobApplications stage only for HIRED
        if data.decision == "HIRED":
            job_application.current_stage = "HIRED"
            job_application.stage_entry_date = timezone_utils.get_ist_now()
            session.add(job_application)

        session.add(candidate_info)
        session.commit()
        session.refresh(candidate_info)
        logger.info(
            f"CandidateInfo updated: application_id={data.application_id} "
            f"decision={data.decision} comment={comment!r}"
        )

        return {
            "success": True,
            "message": f"Final decision updated to {data.decision} for application_id: {data.application_id}",
            "application_id": data.application_id,
            "decision": data.decision,
            "candidate_info_id": candidate_info.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating final decision: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error occurred while updating final decision.",
        )


@router.post("/fetch-interview-analysis")
def fetch_interview_analysis(
    data: FetchInterviewAnalysisRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    try:
        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                and_(
                    models.InterviewAnalysis.analysis_completed == True,
                    models.InterviewAnalysis.application_id == data.application_id,
                )
            )
        ).first()

        if not interview_analysis:
            return {
                "success": True,
                "message": "No interview analyses found",
                "data": {},
            }

        qna_analysis = session.exec(
            select(models.QNA_Analysis).where(
                models.QNA_Analysis.interview_analysis_id == interview_analysis.id
            )
        ).all()

        proctoring_logs = session.exec(
            select(models.ProctoringLogs).where(
                models.ProctoringLogs.interview_analysis_id == interview_analysis.id
            )
        ).all()

        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == interview_analysis.application_id
            )
        ).first()

        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.interview_session_id
                == interview_analysis.interview_session_id
            )
        ).first()

        # Fetch question difficulty counts
        easy_count = 0
        medium_count = 0
        hard_count = 0
        total_questions = 0

        ai_questions = session.exec(
            select(models.AIInterviewQuestions).where(
                models.AIInterviewQuestions.application_id == data.application_id
            )
        ).first()

        questions_list = []
        if ai_questions and ai_questions.questions:
            questions_list = ai_questions.questions
        elif interview_analysis and interview_analysis.questions:
            questions_list = interview_analysis.questions

        if questions_list:
            total_questions = len(questions_list)
            for q in questions_list:
                if isinstance(q, dict):
                    diff = str(q.get("difficulty_level") or "").strip().lower()
                elif hasattr(q, "difficulty_level"):
                    diff = str(getattr(q, "difficulty_level") or "").strip().lower()
                else:
                    diff = ""
                
                if diff == "easy":
                    easy_count += 1
                elif diff == "medium":
                    medium_count += 1
                elif diff == "hard":
                    hard_count += 1

        scheduled_dt_api = (
            timezone_utils.format_datetime_for_api(
                interview_session.interview_scheduled_datetime
            )
            if (
                interview_session
                and getattr(interview_session, "interview_scheduled_datetime", None)
            )
            else None
        )
        started_dt_api = (
            timezone_utils.format_datetime_for_api(
                interview_analysis.interview_started_datetime
            )
            if getattr(interview_analysis, "interview_started_datetime", None)
            else None
        )

        interview_timeline = {}
        interview_timeline["scheduled_dt"] = scheduled_dt_api if scheduled_dt_api else None
        interview_timeline["started_dt"] = started_dt_api if started_dt_api else None


        analysis_data = {
            "application_id": interview_analysis.application_id,
            "status": interview_analysis.status,
            "total_score": interview_analysis.total_score,
            "average_ai_score": interview_analysis.total_score,
            "recommendation": interview_analysis.recommendation,
            "interview_timeline": interview_timeline,
            "candidate_name": (
                f"{job_application.first_name} {job_application.last_name}"
                if job_application
                else "N/A"
            ),
            "candidate_email": job_application.email if job_application else "N/A",
            "total_questions": total_questions or len(interview_analysis.questions),
            "easy_questions_count": easy_count,
            "medium_questions_count": medium_count,
            "hard_questions_count": hard_count,
            "qna_count": len(qna_analysis),
            "qna_analysis": [
                {
                    "id": qna.id,
                    "question_text": qna.question_text,
                    "answer_text": qna.answer_text,
                    **(qna.ai_analysis if qna.ai_analysis else {}),
                    "relevance": (
                        qna.ai_analysis.get("relevance")
                        if qna.ai_analysis and "relevance" in qna.ai_analysis
                        else (qna.ai_analysis.get("job_relevance") if qna.ai_analysis else None)
                    ),
                    "completeness": (
                        qna.ai_analysis.get("completeness")
                        if qna.ai_analysis and "completeness" in qna.ai_analysis
                        else (qna.ai_analysis.get("domain_knowledge") if qna.ai_analysis else None)
                    ),
                    "accuracy": (
                        qna.ai_analysis.get("accuracy")
                        if qna.ai_analysis and "accuracy" in qna.ai_analysis
                        else (qna.ai_analysis.get("problem_solving") if qna.ai_analysis else None)
                    ),
                    "clarity": (
                        qna.ai_analysis.get("clarity")
                        if qna.ai_analysis and "clarity" in qna.ai_analysis
                        else (qna.ai_analysis.get("communication_clarity") if qna.ai_analysis else None)
                    ),
                    "created_at": (
                        timezone_utils.format_datetime_for_api(qna.created_at)
                        if qna.created_at
                        else None
                    ),
                }
                for qna in qna_analysis
            ],
            "proctoring_violations": len(proctoring_logs),
            "proctoring_logs": [
                {
                    "id": log.id,
                    "event_type": log.event_type,
                    "violation_type": log.event_type,
                    "tb_severity": log.tb_severity or "low severity",
                    "severity": log.tb_severity or "low severity",
                    "timestamp": (
                        timezone_utils.format_datetime_for_api(log.timestamp)
                        if log.timestamp
                        else None
                    ),
                    "time": (
                        timezone_utils.format_datetime_for_api(log.timestamp)
                        if log.timestamp
                        else None
                    ),
                    "details": log.details,
                    "description": log.details,
                    "image": log.image_path,
                    "image_path": log.image_path,
                    "image_base64": aws_helper.get_s3_image_base64(log.image_path),
                }
                for log in proctoring_logs
            ],
        }

        if interview_analysis.analysis_completed and not interview_analysis.email_sent:
            send_interview_result_email(interview_analysis, background_tasks, session)

            interview_analysis.email_sent = True
            session.add(interview_analysis)
            session.commit()

        return {
            "success": True,
            "data": analysis_data,
        }

    except Exception as e:
        logger.error(f"Error fetching interview analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch interview analysis.",
        )


@router.get("/fetch-proctoring-images")
def fetch_proctoring_images(
    interview_session_id: str = Query(None),
    session: Session = Depends(deps.get_session),
):
    try:
        s3_result = aws_helper.list_proctoring_images(interview_session_id)

        if s3_result.get("success"):
            return {
                "success": True,
                "interview_session_id": interview_session_id,
                "total_images": len(s3_result.get("images", [])),
                "images": s3_result.get("images"),
            }
        else:
            return {
                "success": False,
                "error": s3_result.get("error"),
                "interview_session_id": interview_session_id,
            }

    except Exception as e:
        logger.error(f"Error fetching proctoring images: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch proctoring images.",
        )


def save_proctoring_violation(interview_session_id: str, alert_type: str, image) -> str:
    try:
        import os

        timestamp_str = timezone_utils.get_ist_now().strftime("%Y%m%d_%H%M%S_%f")
        clean_alert_type = alert_type.replace(" ", "_").lower()
        image_filename = f"violation_{clean_alert_type}_{timestamp_str}.jpg"

        s3_object_name = (
            f"ai-interviews/proctoring/{interview_session_id}/{image_filename}"
        )

        _, buffer = cv2.imencode(".jpg", image)
        image_bytes = buffer.tobytes()

        logger.info(f"Uploading violation image directly to S3")
        upload_result = aws_helper.upload_image_to_s3(image_bytes, s3_object_name)

        if upload_result.get("success"):
            s3_url = upload_result.get("s3_url")
            logger.info(f"Successfully uploaded to S3")
            return s3_url
        else:
            logger.error(f"Failed to upload to S3: {upload_result.get('error')}")
            raise Exception(f"S3 upload failed: {upload_result.get('error')}")

    except Exception as e:
        logger.error(f"Error in save_proctoring_violation: {e}")
        raise e


def get_custom_questions(session: Session, job_id: int) -> List[Dict[str, Any]]:
    import random

    custom_question_limit = consts.MAX_QUESTIONS

    interview_questions = session.exec(
        select(models.InterviewQuestions, models.Questions)
        .join(
            models.Questions,
            models.InterviewQuestions.question_id == models.Questions.question_id,
        )
        .where(models.InterviewQuestions.job_id == job_id)
        .order_by(models.InterviewQuestions.assigned_weightage.desc())
    ).all()

    if not interview_questions:
        logger.warning(f"No custom interview questions found for job_id {job_id}")
        return []

    question_pool = [
        {
            "question_id": question.question_id,
            "question_text": question.question_text,
        }
        for _, question in interview_questions
    ]

    if len(question_pool) <= custom_question_limit:
        selected_questions = question_pool
    else:
        selected_questions = random.sample(question_pool, custom_question_limit)

    return [
        {
            "id": idx + 1,
            "question": question["question_text"],
            "question_id": question["question_id"],
        }
        for idx, question in enumerate(selected_questions)
    ]


def start_interview_generation(interview_session_id: str, session: Session):
    interview_session = session.exec(
        select(models.InterviewSessions).where(
            models.InterviewSessions.interview_session_id == interview_session_id
        )
    ).first()

    if not interview_session:
        return {"error": "Interview Session not found", "questions": []}

    IST = pytz.timezone("Asia/Kolkata")

    config = session.exec(
        select(models.InterviewConfiguration).where(
            models.InterviewConfiguration.configuration_name == "INTERVIEW_EXPIRE_TIME"
        )
    ).first()

    now = datetime.now(IST)

    if interview_session.is_scheduled and interview_session.scheduled_time:
        base_time = interview_session.scheduled_time
        if base_time.tzinfo is None:
            base_time = IST.localize(base_time)
        else:
            base_time = base_time.astimezone(IST)

        expire_minutes = float(config.configuration_value) if config else 30
        start_window = base_time - timedelta(minutes=30)
        expire_time = base_time + timedelta(minutes=expire_minutes)

        if now < start_window:
            return {
                "error": "Interview not yet available. You can join 30 minutes before the scheduled time.",
                "questions": [],
                "available_at": start_window,
            }

        # if now > expire_time:
        #     return {
        #         "error": "Interview session expired",
        #         "questions": [],
        #         "expired_at": expire_time,
        #     }
    else:
        expire_minutes = float(config.configuration_value) if config else 120
        created_time = interview_session.created_date

        if created_time.tzinfo is None:
            created_time = IST.localize(created_time)
        else:
            created_time = created_time.astimezone(IST)

        expire_time = created_time + timedelta(minutes=expire_minutes)

        if now > expire_time:
            return {
                "error": "Interview session expired",
                "questions": [],
                "expired_at": expire_time,
            }

    question_type = interview_session.question_type

    interview_analysis = session.exec(
        select(models.InterviewAnalysis).where(
            models.InterviewAnalysis.interview_session_id
            == interview_session.interview_session_id
        )
    ).first()

    # if (
    #     interview_analysis
    #     and interview_analysis.status == models.StatusEnum.in_progress
    # ):
    #     return {"error": "Interview is already started", "questions": []}
    if True:
        pass
    elif (
        interview_analysis and interview_analysis.status == models.StatusEnum.completed
    ):
        return {"error": "Interview is already completed", "questions": []}

    elif (
        interview_analysis
        and interview_analysis.status == models.StatusEnum.not_started
    ):
        interview_analysis.application_id = interview_session.application_id
        interview_analysis.status = models.StatusEnum.in_progress
        if getattr(interview_analysis, "interview_started_datetime", None) is None:
            interview_analysis.interview_started_datetime = timezone_utils.get_ist_now()
    else:
        job_app = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == interview_session.application_id
            )
        ).first()
        interview_analysis = models.InterviewAnalysis(
            application_id=interview_session.application_id,
            interview_session_id=interview_session.interview_session_id,
            status=models.StatusEnum.in_progress,
            job_id=job_app.job_id if job_app else None,
            interview_started_datetime=timezone_utils.get_ist_now(),
        )

    session.add(interview_session)

    job_details = session.exec(
        select(models.JobDetails)
        .join(
            models.JobApplications,
            models.JobDetails.job_id == models.JobApplications.job_id,
        )
        .where(models.JobApplications.id == interview_session.application_id)
    ).first()

    job = session.exec(
        select(models.Jobs).where(models.Jobs.job_id == job_details.job_id)
    ).first()

    structured_questions = []

    # 1. Try to fetch from tb_ai_interview_questions first
    ai_questions = session.exec(
        select(models.AIInterviewQuestions).where(
            models.AIInterviewQuestions.application_id == interview_session.application_id
        )
    ).first()

    if ai_questions and ai_questions.questions:
        logger.info(f"Using pre-existing questions from tb_ai_interview_questions for application {interview_session.application_id}")
        structured_questions = ai_questions.questions
    elif interview_analysis and interview_analysis.questions:
        logger.info(f"Using pre-existing questions from tb_interview_analysis for application {interview_session.application_id}")
        structured_questions = interview_analysis.questions

    # 2. If no questions exist, generate them
    if not structured_questions:
        if question_type == "CUSTOM":
            logger.info(f"Fetching custom questions for job {job_details.job_id}")
            structured_questions = get_custom_questions(session, job_details.job_id)

            if len(structured_questions) < 5:
                logger.warning(
                    f"No custom questions found for job {job_details.job_id}. Falling back to AI."
                )
                question_type = "AI"

        if question_type == "AI":
            resume_analysis = session.exec(
                select(models.ResumeAnalysis).where(
                    models.ResumeAnalysis.application_id == interview_session.application_id
                )
            ).first()

            resume_parser = S3ResumeParser()
            resume_text_response = resume_parser.extract_text(resume_analysis.file_path)
            if isinstance(resume_text_response, dict):
                resume_text = resume_text_response.get("text", "") or "No resume text available."
            else:
                resume_text = resume_text_response or "No resume text available."

            job_description = utils.construct_job_description_for_llm(
                job_title=db_operations.get_job_title(session, job_details.job_id),
                job_info=job.job_info,
                job_description=job_details.job_description,
                job_requirements=job_details.job_requirements,
                qualification=job_details.qualification,
                skills=job_details.skills,
            )

            technial_interviewer = AIInterviewer(
                job_role=db_operations.get_job_title(session, job_details.job_id),
                job_description=job_description,
                experience=resume_analysis.experience_level,
                skills=job_details.skills,
                topics=resume_analysis.interview_focus_areas,
                resume_text=resume_text,
            )

            questions = technial_interviewer.generate_questions()

            structured_questions = []
            technical_count = len(questions) // 2 if len(questions) % 2 == 0 else (len(questions) // 2 + 1)
            for idx, question in enumerate(questions):
                q_type = "technical" if idx < technical_count else "behavioural"
                structured_questions.append({
                    "question_id": idx + 1,
                    "question": question,
                    "expected_time": "2-3 mins",
                    "difficulty_level": "medium",
                    "question_type": q_type
                })

            # Save generated questions to tb_ai_interview_questions for persistence
            if not ai_questions:
                ai_questions = models.AIInterviewQuestions(
                    application_id=interview_session.application_id,
                    number_of_questions=len(structured_questions),
                    difficulty_level="Medium",
                    question_type=["technical"],
                    questions=structured_questions
                )
            else:
                ai_questions.questions = structured_questions
                ai_questions.number_of_questions = len(structured_questions)
            session.add(ai_questions)

    interview_analysis.questions = structured_questions
    interview_analysis.status = models.StatusEnum.in_progress

    session.add(interview_analysis)
    session.commit()
    session.refresh(interview_analysis)

    return {"questions": structured_questions}


@router.post("/start")
def start_interview(
    data: StartInterviewRequest,
    session: Session = Depends(deps.get_session),
    # _seb: bool = Depends(verify_seb),
):
    logger.info(f"start-interview for session {data.interview_session_id}")
    
    interview_session = session.exec(
        select(models.InterviewSessions).where(
            models.InterviewSessions.interview_session_id == data.interview_session_id
        )
    ).first()

    if not interview_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found.",
        )

    response = start_interview_generation(data.interview_session_id, session)

    if response.get("error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=response["error"],
        )

    response["MAX_QUESTION_TIME"] = consts.MAX_QUESTION_TIME
    response["IMAGE_PROCTORING_TIME_WINDOW"] = consts.IMAGE_PROCTORING_TIME_WINDOW
    return response


@router.post("/submit-answers")
async def submit_answers(
    data: SubmitAnswersRequest,
    session: Session = Depends(deps.get_session),
    # _seb: bool = Depends(verify_seb),
):
    import asyncio

    logger.info(f"submit-answers for session {data.interview_session_id}")
    interview_session_id = data.interview_session_id

    interview_analysis = session.exec(
        select(models.InterviewAnalysis).where(
            models.InterviewAnalysis.interview_session_id == interview_session_id
        )
    ).first()

    if not interview_analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    if interview_analysis.status == models.StatusEnum.not_started:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview not started yet. Please start the interview first.",
        )

    if interview_analysis.status == models.StatusEnum.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Interview already completed. Cannot submit more answers.",
        )
    import asyncio

    try:
        analysis_id = interview_analysis.id

        def run_create_pending():
            audio_s3_keys = {}
            for q_id, audio_b64 in data.audios.items():
                audio_bytes = base64.b64decode(audio_b64)
                timestamp_str = timezone_utils.get_ist_now().strftime(
                    "%Y%m%d_%H%M%S_%f"
                )
                filename = f"audio_{interview_session_id}_{q_id}_{timestamp_str}.wav"
                s3_key = f"ai-interviews/audio/{interview_session_id}/{filename}"

                result = aws_helper.upload_audio_to_s3(audio_bytes, s3_key)
                if result.get("success"):
                    audio_s3_keys[q_id] = s3_key
                    logger.info(f"[submit-answers] Q{q_id} uploaded to MinIO: {s3_key}")
                else:
                    logger.error(
                        f"[submit-answers] Q{q_id} MinIO upload failed: {result.get('error')}"
                    )
                    raise Exception(
                        f"MinIO upload failed for Q{q_id}: {result.get('error')}"
                    )

            logger.info(
                f"[submit-answers] All {len(audio_s3_keys)} audios uploaded. Creating pending answers..."
            )

            from app.db.session import engine

            with Session(engine) as db_session:
                res = db_operations.create_pending_answers(
                    db_session,
                    interview_session_id,
                    audio_s3_keys,
                )

                if res.get("success"):
                    bg_analysis = db_session.exec(
                        select(models.InterviewAnalysis).where(
                            models.InterviewAnalysis.interview_session_id
                            == interview_session_id
                        )
                    ).first()

                    if bg_analysis:
                        bg_analysis.status = models.StatusEnum.completed
                        bg_analysis.interview_analysis_date = (
                            timezone_utils.get_ist_now()
                        )
                        db_session.add(bg_analysis)

                        session_obj = db_session.exec(
                            select(models.InterviewSessions).where(
                                models.InterviewSessions.interview_session_id
                                == interview_session_id
                            )
                        ).first()
                        if session_obj:
                            session_obj.status = (
                                models.InterviewSessionStatusEnum.completed
                            )
                            db_session.add(session_obj)

                        db_session.commit()
                return res

        db_result = await asyncio.to_thread(run_create_pending)

        if db_result.get("success"):
            return {
                "message": "answers-submitted",
                "status": "processing",
                "detail": "Answers received and queued for analysis.",
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to queue answers",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in submit-answers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.post("/move-to-schedule")
def move_to_schedule(
    data: MoveToScheduleRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    """
    Update the move_to_schedule status for an interview session.
    """
    logger.info(f"move-to-schedule for session {data.application_id}")
    
    interview_session = session.exec(
        select(models.InterviewSessions).where(
            models.InterviewSessions.application_id == data.application_id
        )
    ).first()

    if not interview_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found.",
        )

    interview_session.move_to_schedule = True
    interview_session.move_to_schedule_datetime = timezone_utils.get_ist_now()
    interview_session.status = models.InterviewSessionStatusEnum.scheduled

    try:
        interview_emails.send_interview_invitation(
            interview_session, background_tasks, session
        )
        logger.info(f"Successfully scheduled and sent interview invite email to candidate for session {interview_session.interview_session_id}")
    except Exception as e:
        logger.error(f"Failed to send interview invitation email for session {interview_session.interview_session_id}: {e}")

    session.add(interview_session)
    session.commit()
    session.refresh(interview_session)
    
    return {
        "success": True,
        "message": f"Successfully moved to schedule for application {data.application_id}",
    }


@router.post("/finalize-questions", response_model=FinalizeQuestionsResponse)
def finalize_questions(
    data: FinalizeQuestionsRequest,
    session: Session = Depends(deps.get_session),
):
    """
    Finalize and save questions for an interview session.
    This endpoint receives the final list of questions (after edits/deletions/additions)
    and stores them in the database.
    """
    logger.info(f"finalize-questions for application {data.application_id}")
    
    try:
        # Get the interview session
        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id == data.application_id
            )
        ).first()

        if not interview_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview session not found.",
            )

        # Get the job application to link with questions
        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == data.application_id
            )
        ).first()

        if not job_application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job application not found.",
            )

        # Process and preserve finalized questions format from request body
        finalized_questions = []
        for idx, q in enumerate(data.questions):
            q_dict = None
            if hasattr(q, "model_dump"):
                q_dict = q.model_dump()
            elif hasattr(q, "dict"):
                q_dict = q.dict()
            elif isinstance(q, dict):
                q_dict = dict(q)
                
            if q_dict is not None:
                if "question_id" not in q_dict:
                    q_dict["question_id"] = idx + 1
                finalized_questions.append(q_dict)
            else:
                finalized_questions.append({
                    "question_id": idx + 1,
                    "question": str(q),
                    "question_type": "technical",
                    "difficulty_level": "Medium",
                    "expected_time": "2-3 mins"
                })



        # Check if AIInterviewQuestions record exists
        ai_interview_questions = session.exec(
            select(models.AIInterviewQuestions).where(
                models.AIInterviewQuestions.application_id == data.application_id
            )
        ).first()

        if ai_interview_questions:
            # Update existing record
            ai_interview_questions.questions = finalized_questions
            ai_interview_questions.number_of_questions = len(finalized_questions)
            session.add(ai_interview_questions)
            logger.info(f"Updated finalized questions for application {data.application_id}")
        else:
            # Create new record if it doesn't exist
            ai_interview_questions = models.AIInterviewQuestions(
                application_id=data.application_id,
                number_of_questions=len(finalized_questions),
                difficulty_level="Medium",
                question_type=["technical", "behavioural"],
                questions=finalized_questions,
                job_id=job_application.job_id,
            )
            session.add(ai_interview_questions)
            logger.info(f"Created new finalized questions record for application {data.application_id}")

        # Also update the InterviewAnalysis if it exists
        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                models.InterviewAnalysis.application_id == data.application_id
            )
        ).first()

        if interview_analysis:
            interview_analysis.questions = finalized_questions
            session.add(interview_analysis)
            logger.info(f"Updated interview analysis with finalized questions")

        # Mark questions as generated and update pass criteria if provided
        interview_session.questions_status = True
        if data.min_pass_percentage is not None:
            interview_session.min_pass_percentage = data.min_pass_percentage
        if data.acceptable_score_range is not None:
            interview_session.acceptable_score_range = data.acceptable_score_range
        session.add(interview_session)

        session.commit()

        return FinalizeQuestionsResponse(
            success=True,
            message="Questions finalized and saved successfully",
            application_id=data.application_id,
            questions_count=len(finalized_questions),
            finalized_at=timezone_utils.get_ist_now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in finalize-questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to finalize questions: {str(e)}",
        )


@router.get("/candidate-details")
def get_candidate_details(
    interview_session_id: str = Query(...),
    session: Session = Depends(deps.get_session),
):
    logger.info(f"get-candidate-details for session {interview_session_id}")

    try:
        job_application = session.exec(
            select(models.JobApplications)
            .join(
                models.InterviewSessions,
                models.JobApplications.id == models.InterviewSessions.application_id,
            )
            .where(
                models.InterviewSessions.interview_session_id == interview_session_id
            )
        ).first()

        if not job_application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Candidate not found for this interview session.",
            )

        job_details = session.exec(
            select(models.JobDetails).where(
                models.JobDetails.job_id == job_application.job_id
            )
        ).first()

        full_name = job_application.first_name + " " + job_application.last_name
        email = job_application.email
        job_title = db_operations.get_job_title(session, job_details.job_id)

        return {
            "message": "candidate-details",
            "full_name": full_name,
            "email": email,
            "job_title": job_title,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting candidate details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.post("/proctoring-log")
def create_proctoring_log(
    data: ProctoringLogRequest,
    session: Session = Depends(deps.get_session),
    # _seb: bool = Depends(verify_seb),
):
    logger.info(f"create-proctoring-log for session {data.interview_session_id}")

    if data.event_type not in models.ProctoringEventType._value2member_map_:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event_type: {data.event_type}",
        )

    try:
        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                models.InterviewAnalysis.interview_session_id
                == data.interview_session_id
            )
        ).first()

        if not interview_analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview session not found.",
            )

        event_type_str = str(data.event_type)
        tb_sev = "low severity"
        if event_type_str in [models.ProctoringEventType.visual_violation, models.ProctoringEventType.clipboard_violation, "Visual Violation", "Clipboard Violation"]:
            tb_sev = "high severity"
        elif event_type_str in [
            models.ProctoringEventType.browser_tab_switch,
            models.ProctoringEventType.right_click_blocked,
            models.ProctoringEventType.fullscreen_exit,
            models.ProctoringEventType.fullscreen_auto_reenter,
            models.ProctoringEventType.esc_key_attempt,
            models.ProctoringEventType.forbidden_key_attempt,
            "BROWSER_TAB_SWITCH",
            "RIGHT_CLICK_BLOCKED",
            "FULLSCREEN_EXIT",
            "FULLSCREEN_AUTO_REENTER",
            "ESC_KEY_ATTEMPT",
            "FORBIDDEN_KEY_ATTEMPT"
        ]:
            tb_sev = "Medium severity"

        proctoring_log = models.ProctoringLogs(
            interview_analysis_id=interview_analysis.id,
            event_type=data.event_type,
            details=data.details,
            tb_severity=tb_sev,
        )

        session.flush()
        session.add(proctoring_log)
        session.commit()
        session.refresh(proctoring_log)

        return {"message": "Proctoring Log Created", "id": proctoring_log.id}

    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Error creating proctoring log: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.post("/analyze-image", status_code=status.HTTP_202_ACCEPTED)
def analyze_image(
    data: AnalyzeImageRequest,
):
    logger.info(f"analyze-image enqueue for session {data.interview_session_id}")

    from app.services import kafka_helper

    import uuid

    image_base64 = data.image_base64
    try:
        if image_base64.startswith("data:image"):
            header, b64_data = image_base64.split(",", 1)
        else:
            header = "data:image/jpeg;base64"
            b64_data = image_base64

        image_data = base64.b64decode(b64_data)
        image_array = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if image is not None:
            max_dim = 640
            quality = 70

            while True:
                h, w = image.shape[:2]
                if max(h, w) > max_dim:
                    scale = max_dim / max(h, w)
                    resized_image = cv2.resize(image, (int(w * scale), int(h * scale)))
                else:
                    resized_image = image

                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
                _, buffer = cv2.imencode(".jpg", resized_image, encode_param)
                encoded_b64 = base64.b64encode(buffer).decode("utf-8")

                if len(encoded_b64) < 220000:
                    image_base64 = f"{header},{encoded_b64}"
                    break

                max_dim = int(max_dim * 0.8)
                quality = max(20, quality - 10)

                if max_dim < 150 or quality <= 20:
                    image_base64 = f"{header},{encoded_b64}"
                    break

    except Exception as e:
        logger.warning(f"Failed to compress image before Kafka: {e}")

    payload = {
        "interview_session_id": data.interview_session_id,
        "image_base64": image_base64,
    }

    if len(json_dumps(payload).encode("utf-8")) > 250000:
        logger.error("Payload still exceeds 250KB despite compression.")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image resolution is too high and cannot be compressed sufficiently.",
        )

    result = kafka_helper.send_analyze_image_task(
        payload=payload,
        message_group_id=data.interview_session_id,
    )

    if not result.get("success"):
        logger.error(f"Failed to enqueue analyze-image: {result.get('error')}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to queue image for analysis. Please retry.",
        )

    return {
        "message": "analyze-image-queued",
        "status": "processing",
        "detail": "Image queued for proctoring analysis.",
    }


# --- Test apis ---


@router.post("/test-send-interview-email")
def test_email(
    data: TestSendInterviewEmailRequest,
    session: Session = Depends(deps.get_session),
):
    from app.services.email.interview_emails import send_interview_link_email_sync
    from app.models import InterviewSessions

    interview_session = session.exec(
        select(InterviewSessions).where(
            InterviewSessions.interview_session_id == data.interview_session_id
        )
    ).first()
    if not interview_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found.",
        )
    sent = send_interview_link_email_sync(interview_session, session)
    return {"message": "Email sent triggered successfully", "sent": sent}


@router.post("/generate-ai-questions", response_model=GenerateAIQuestionsResponse)
def generate_ai_questions(
    data: GenerateAIQuestionsRequest,
    session: Session = Depends(deps.get_session),
):
    logger.info(f"generate-ai-questions for application_id: {data.application_id}")
    try:


        resume_analysis = session.exec(
            select(models.ResumeAnalysis).where(
                models.ResumeAnalysis.application_id == data.application_id
            )
        ).first()
        if not resume_analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resume analysis not found for application_id: {data.application_id}",
            )

        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == data.application_id
            )
        ).first()
        if not job_application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job application not found for application_id: {data.application_id}",
            )

        job_details = session.exec(
            select(models.JobDetails).where(
                models.JobDetails.job_id == job_application.job_id
            )
        ).first()
        if not job_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job details not found for job_id: {job_application.job_id}",
            )

        job = session.exec(
            select(models.Jobs).where(models.Jobs.job_id == job_details.job_id)
        ).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job not found for job_id: {job_details.job_id}",
            )

        resume_parser = S3ResumeParser()
        resume_text_response = resume_parser.extract_text(resume_analysis.file_path)
        if isinstance(resume_text_response, dict):
            resume_text = resume_text_response.get("text", "") or "No resume text available."
        else:
            resume_text = resume_text_response or "No resume text available."

        job_description = utils.construct_job_description_for_llm(
            job_title=db_operations.get_job_title(session, job_details.job_id),
            job_info=job.job_info,
            job_description=job_details.job_description,
            job_requirements=job_details.job_requirements,
            qualification=job_details.qualification,
            skills=job_details.skills,
        )

        technial_interviewer = AIInterviewer(
            job_role=db_operations.get_job_title(session, job_details.job_id),
            job_description=job_description,
            experience=resume_analysis.experience_level,
            skills=job_details.skills,
            topics=resume_analysis.interview_focus_areas,
            resume_text=resume_text,
        )

        questions_response = technial_interviewer.generate_custom_questions(
            count=data.number_of_questions,
            difficulty=data.difficulty_level,
            question_types=data.question_type,
        )

        # Standardize questions format in questions_response without saving to DB
        if questions_response and "questions" in questions_response:
            new_questions = []
            for idx, q in enumerate(questions_response["questions"]):
                if isinstance(q, dict):
                    q["question_id"] = idx + 1
                    if "difficulty_level" in q:
                        q["difficulty_level"] = str(q["difficulty_level"]).lower()
                    if "question_type" in q:
                        q["question_type"] = str(q["question_type"]).lower()
                    new_questions.append(q)
                else:
                    new_questions.append({
                        "question_id": idx + 1,
                        "question": str(q),
                        "expected_time": "2-3 mins",
                        "difficulty_level": data.difficulty_level.lower(),
                        "question_type": data.question_type[0].lower() if data.question_type else "technical"
                    })
            questions_response = {
                "total_questions": len(new_questions),
                "questions": new_questions
            }

        return questions_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate-ai-questions endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while generating AI questions.",
        )


@router.get("/get-all-generate-ai-questions", response_model=GenerateAIQuestionsResponse)
def get_generated_ai_questions(
    application_id: int = Query(...),
    session: Session = Depends(deps.get_session),
):
    logger.info(f"get-generated-ai-questions for application_id: {application_id}")
    try:
        ai_questions = session.exec(
            select(models.AIInterviewQuestions).where(
                models.AIInterviewQuestions.application_id == application_id
            )
        ).first()

        if not ai_questions:
            raise HTTPException(
                status_code=status.HTTP_204_NO_CONTENT,
                detail=f"AI generated questions not found for application_id: {application_id}",
            )

        returned_questions = []
        for q in ai_questions.questions:
            if isinstance(q, dict):
                returned_questions.append({
                    "question_id": q.get("question_id") or q.get("id") or 1,
                    "question": q.get("question") or q.get("question_text") or "",
                    "expected_time": q.get("expected_time") or "2-3 mins",
                    "difficulty_level": q.get("difficulty_level") or "medium",
                    "question_type": q.get("question_type") or "technical"
                })

        return {
            "total_questions": len(returned_questions),
            "questions": returned_questions
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching AI generated questions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching AI questions.",
        )


@router.post("/custom-question", response_model=GenerateAIQuestionsResponse)
def add_custom_question(
    data: AddCustomQuestionRequest,
    session: Session = Depends(deps.get_session),
):
    logger.info(f"add-custom-question for application_id: {data.application_id}")
    try:
        # Check/create InterviewSession and InterviewAnalysis if they don't exist yet
        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id == data.application_id
            )
        ).first()

        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                models.InterviewAnalysis.application_id == data.application_id
            )
        ).first()

        if not interview_session or not interview_analysis:
            job_app = session.exec(
                select(models.JobApplications).where(
                    models.JobApplications.id == data.application_id
                )
            ).first()
            if not job_app:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job application not found for application_id: {data.application_id}",
                )
            
            if not interview_session:
                interview_session_id = str(uuid4())
                interview_session = models.InterviewSessions(
                    interview_session_id=interview_session_id,
                    application_id=data.application_id,
                    question_type="AI",
                    status=models.InterviewSessionStatusEnum.scheduled,
                    exam_exit_password="",
                    job_id=job_app.job_id,
                )
                session.add(interview_session)
                session.flush()
            else:
                interview_session_id = interview_session.interview_session_id

            if not interview_analysis:
                interview_analysis = models.InterviewAnalysis(
                    application_id=data.application_id,
                    interview_session_id=interview_session_id,
                    status=models.StatusEnum.not_started,
                    questions=[],
                    job_id=job_app.job_id,
                )
                session.add(interview_analysis)
            
            session.commit()

        # Retrieve current question list from request data, falling back to DB if not provided
        questions = []
        if data.existing_questions is not None:
            questions = list(data.existing_questions)
        else:
            # Fallback to check DB
            ai_questions = session.exec(
                select(models.AIInterviewQuestions).where(
                    models.AIInterviewQuestions.application_id == data.application_id
                )
            ).first()
            if ai_questions:
                questions = list(ai_questions.questions or [])
            elif interview_analysis and interview_analysis.questions:
                questions = list(interview_analysis.questions)

        # Calculate next question_id
        next_id = 1
        if questions:
            ids = [q.get("question_id") or q.get("id") or 0 for q in questions if isinstance(q, dict)]
            next_id = max(ids) + 1 if ids else len(questions) + 1

        new_q = {
            "question_id": next_id,
            "question": data.question,
            "expected_time": data.expected_time,
            "difficulty_level": data.difficulty_level.lower(),
            "question_type": data.question_type.lower(),
        }
        questions.append(new_q)
        
        # Standardize return questions format WITHOUT saving to DB
        returned_questions = []
        for q in questions:
            if isinstance(q, dict):
                returned_questions.append({
                    "question_id": q.get("question_id") or q.get("id") or 1,
                    "question": q.get("question") or q.get("question_text") or "",
                    "expected_time": q.get("expected_time") or "2-3 mins",
                    "difficulty_level": q.get("difficulty_level") or "medium",
                    "question_type": q.get("question_type") or "technical"
                })

        return {
            "total_questions": len(returned_questions),
            "questions": returned_questions
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding custom question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add custom question.",
        )


@router.put("/custom-question")
def update_custom_question(
    data: UpdateCustomQuestionRequest,
    session: Session = Depends(deps.get_session),
):
    logger.info(f"update-custom-question for application_id: {data.application_id}, question_id: {data.question_id}")
    try:
        # Check if InterviewSession exists
        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id == data.application_id
            )
        ).first()
        if not interview_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview session not found.",
            )

        # Do NOT update/save any drafts to database tables.
        # The frontend manages the in-memory state and sends the final list of questions to /finalize-questions.
        return {
            "status": "success",
            "message": "Question updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating custom question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update custom question.",
        )


@router.delete("/custom-question")
def delete_custom_question(
    data: DeleteCustomQuestionRequest,
    session: Session = Depends(deps.get_session),
):
    logger.info(f"delete-custom-question for application_id: {data.application_id}, question_id: {data.question_id}")
    try:
        # Check if InterviewSession exists
        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id == data.application_id
            )
        ).first()
        if not interview_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview session not found.",
            )

        # Do NOT delete/save any drafts to database tables.
        # The frontend manages the in-memory state and sends the final list of questions to /finalize-questions.
        return {
            "status": "success",
            "message": "Question deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting custom question: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete custom question.",
        )

def process_live_frame_sync(session_id: str, data: str):
    from app.services.ai_interviewer.proctoring import ProctoringEngine
    from app.db.session import engine
    from sqlmodel import Session, select
    from app import models
    import json
    from io import BytesIO
    from app.utils import timezone_utils
    from app.services import minio_helper as aws_helper
    
    try:
        # 1. Decode base64 image
        if data.startswith("data:image"):
            header, b64_data = data.split(",", 1)
        else:
            b64_data = data
            
        image_data = base64.b64decode(b64_data)
        image_array = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is None:
            return None, None
            
        # 2. Run proctoring engine
        engine_instance = ProctoringEngine()
        result = engine_instance.analyze_frame(image)
        alerts = result.get("alerts", [])
        metrics = result.get("metrics", {})
        print(alerts)
        # 3. Log to DB and MinIO if there are alerts
        if alerts:
            with Session(engine) as db_session:
                interview_analysis = db_session.exec(
                    select(models.InterviewAnalysis).where(
                        models.InterviewAnalysis.interview_session_id == session_id
                    )
                ).first()
                # print(interview_analysis)
                
                if interview_analysis:
                    try:
                        timestamp_str = timezone_utils.get_ist_now().strftime("%Y%m%d_%H%M%S_%f")
                        clean_alert_type = alerts[0].replace(" ", "_").lower()
                        
                        # Save violation image to MinIO/S3
                        image_filename = f"live_violation_{clean_alert_type}_{timestamp_str}.jpg"
                        s3_object_name = f"ai-interviews/proctoring/{session_id}/{image_filename}"
                        
                        _, buffer = cv2.imencode(".jpg", image)
                        image_bytes = buffer.tobytes()
                        
                        upload_result = aws_helper.upload_image_to_s3(image_bytes, s3_object_name)
                        image_path = upload_result.get("s3_url") if upload_result.get("success") else None
                        
                        # Save proctoring log JSON file to MinIO/S3
                        log_filename = f"live_log_{clean_alert_type}_{timestamp_str}.json"
                        log_s3_object_name = f"ai-interviews/proctoring/{session_id}/{log_filename}"
                        log_payload = {
                            "session_id": session_id,
                            "alerts": alerts,
                            "metrics": metrics,
                            "timestamp": timezone_utils.get_ist_now().isoformat(),
                            "image_path": image_path
                        }
                        log_bytes = json.dumps(log_payload, indent=2).encode("utf-8")
                        
                        # Upload JSON file to MinIO bucket
                        minio_client = aws_helper.get_minio_client()
                        if minio_client:
                            bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
                            aws_helper.ensure_bucket_exists(bucket_name)
                            minio_client.put_object(
                                bucket_name,
                                log_s3_object_name,
                                data=BytesIO(log_bytes),
                                length=len(log_bytes),
                                content_type="application/json"
                            )
                        
                        # Save to SQL DB log
                        proctoring_log = models.ProctoringLogs(
                            interview_analysis_id=interview_analysis.id,
                            event_type=models.ProctoringEventType.visual_violation,
                            details=json.dumps(alerts),
                            image_path=image_path,
                            tb_severity="high severity",
                        )
                        db_session.add(proctoring_log)
                        db_session.commit()
                    except Exception as err:
                        logger.error(f"Error logging live proctoring violation: {err}")
        return alerts, metrics
    except Exception as e:
        logger.error(f"Error processing live frame: {e}")
        return None, None


async def run_background_detection(session_id: str, data: str):
    import asyncio
    try:
        # Run process_live_frame_sync in a thread pool silently
        await asyncio.to_thread(process_live_frame_sync, session_id, data)
    except Exception as e:
        logger.error(f"Error in background live monitoring detection for session {session_id}: {e}")
    finally:
        # Reset is_processing flag
        state = stream_manager.get_proctoring_state(session_id)
        state["is_processing"] = False


@router.websocket("/ws/live-monitoring/{session_id}")
async def live_monitoring_stream(websocket: WebSocket, session_id: str):
    import asyncio
    import time
    logger.info(f"WebSocket live monitoring request received for session: {session_id}")
    await stream_manager.connect(session_id, websocket)
    try:
        while True:
            # Receive video frame (Base64 string or binary) from candidate
            data = await websocket.receive_text()
            
            # 1. Forward the video frame IMMEDIATELY for lag-free video stream
            await stream_manager.broadcast_frame(session_id, data, sender=websocket)
            
            # 2. Asynchronously evaluate proctoring violations without blocking
            if data.startswith("data:image"):
                state = stream_manager.get_proctoring_state(session_id)
                current_time = time.time()
                
                # Check rate-limit (3 seconds) and guarantee no parallel detection runs
                if not state["is_processing"] and (current_time - state["last_detection_time"] >= 3.0):
                    state["is_processing"] = True
                    state["last_detection_time"] = current_time
                    asyncio.create_task(run_background_detection(session_id, data))
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket live monitoring connection disconnected for session: {session_id}")
        stream_manager.disconnect(session_id, websocket)
    except Exception as e:
        logger.error(f"Error in live monitoring WebSocket for session {session_id}: {e}")
        stream_manager.disconnect(session_id, websocket)