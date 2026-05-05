from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlmodel import Session, select
from app import models
from app.api import deps
from app.schemas import *
from app.core import config as consts
from uuid import uuid4
from app.services.email import interview_emails
from app.services.ai_interviewer.ai_interviewer import AIInterviewer
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interview Session is already created for candidate: {data.application_id}",
        )

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
            status=models.InterviewSessionStatusEnum.scheduled,
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

        return {
            "success": True,
            "application_id": interview_session.application_id,
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
        interview_session.status = models.InterviewSessionStatusEnum.scheduled

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

        # --- Look up (or auto-create) the interview session ---
        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id == data.application_id,
                models.InterviewSessions.is_deleted == False,
            )
        ).first()

        if not interview_session:
            logger.info(
                f"No interview session found for application_id {data.application_id}. "
                "Auto-creating one before scheduling."
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

            interview_session_id = str(uuid4())

            interview_session = models.InterviewSessions(
                interview_session_id=interview_session_id,
                application_id=data.application_id,
                question_type=data.question_type,
                exam_exit_password="",
                status=models.InterviewSessionStatusEnum.scheduled,
            )

            session.add(interview_session)
            session.flush()

            # Only create InterviewAnalysis if one doesn't already exist
            existing_analysis = session.exec(
                select(models.InterviewAnalysis).where(
                    models.InterviewAnalysis.application_id == data.application_id,
                )
            ).first()

            if not existing_analysis:
                interview_analysis = models.InterviewAnalysis(
                    application_id=data.application_id,
                    interview_session_id=interview_session_id,
                    status=models.StatusEnum.not_started,
                    questions=[],
                    job_id=job_application.job_id,
                )
                session.add(interview_analysis)

            session.commit()
            session.refresh(interview_session)

            logger.info(
                f"Auto-created interview session {interview_session_id} "
                f"for application_id {data.application_id}"
            )

        # --- Schedule the interview ---
        dt_str = f"{data.scheduled_date} {data.scheduled_time}"
        slot_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

        interview_session.scheduled_time = slot_dt
        interview_session.is_scheduled = True
        interview_session.schedule_email_sent = False
        interview_session.status = models.InterviewSessionStatusEnum.scheduled

        session.add(interview_session)
        session.commit()
        session.refresh(interview_session)

        # --- Send schedule confirmation email only ---
        interview_emails.send_schedule_confirmation_email(
            interview_session, background_tasks, session
        )

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

        analysis_data = {
            "application_id": interview_analysis.application_id,
            "status": interview_analysis.status,
            "total_score": interview_analysis.total_score,
            "recommendation": interview_analysis.recommendation,
            "candidate_name": (
                f"{job_application.first_name} {job_application.last_name}"
                if job_application
                else "N/A"
            ),
            "candidate_email": job_application.email if job_application else "N/A",
            "total_questions": len(interview_analysis.questions),
            "qna_count": len(qna_analysis),
            "qna_analysis": [
                {
                    "id": qna.id,
                    "question_text": qna.question_text,
                    "answer_text": qna.answer_text,
                    **(qna.ai_analysis if qna.ai_analysis else {}),
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
                    "timestamp": (
                        timezone_utils.format_datetime_for_api(log.timestamp)
                        if log.timestamp
                        else None
                    ),
                    "details": log.details,
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
        resume_text = resume_parser.extract_text(resume_analysis.file_path)

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

        structured_questions = [
            {"id": idx + 1, "question": question}
            for idx, question in enumerate(questions)
        ]

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

        proctoring_log = models.ProctoringLogs(
            interview_analysis_id=interview_analysis.id,
            event_type=data.event_type,
            details=data.details,
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
