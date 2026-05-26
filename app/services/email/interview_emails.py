import logging
from fastapi import BackgroundTasks, HTTPException, status
from app.services.email.email_service import (
    send_email,
    get_candidate_details,
    get_cutoff_score,
)
from app.core import config as consts
from app import models
from sqlmodel import Session
import os
import tempfile
from app.services.seb.seb_config import build_seb_config
import hashlib
from app.utils import utils

logger = logging.getLogger(__name__)


def send_interview_invitation(
    interview_session: models.InterviewSessions,
    background_tasks: BackgroundTasks,
    db_session: Session,
):
    link = f"{consts.INTERVIEW_FRONTEND}/requirement-download/schedule/{interview_session.interview_session_id}/"
    if type(interview_session) is not models.InterviewSessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Interview Session not found"
        )
    job_title, candidate_name, candidate_email = get_candidate_details(
        interview_session.application_id, db_session
    )
    try:

        background_tasks.add_task(
            send_email,
            subject=f"Action Required: Schedule your interview for {job_title}",
            template_name="emails/interview_invite.html",
            context={"candidate_name": candidate_name, "role": job_title, "link": link},
            recipients=[candidate_email],
        )
        logger.info("AI Interview Invitation E-mail Sent (Schedule Link)")
    except Exception as err:
        raise Exception(err)


def send_schedule_confirmation_email(
    interview_session: models.InterviewSessions,
    background_tasks: BackgroundTasks,
    db_session: Session,
):
    if type(interview_session) is not models.InterviewSessions:
        raise HTTPException(status_code=404, detail="Session not found")

    job_title, candidate_name, candidate_email = get_candidate_details(
        interview_session.application_id, db_session
    )
    dt_str = (
        interview_session.scheduled_time.strftime("%A, %B %d, %Y at %I:%M %p")
        if interview_session.scheduled_time
        else "TBD"
    )

    try:
        background_tasks.add_task(
            send_email,
            subject=f"Interview Scheduled: {job_title}",
            template_name="emails/schedule_confirmation.html",
            context={
                "candidate_name": candidate_name,
                "role": job_title,
                "scheduled_time": dt_str,
            },
            recipients=[candidate_email],
        )
        logger.info(f"Schedule confirmation email sent to {candidate_email}")
    except Exception as err:
        logger.error(err)
        raise Exception(err)


import asyncio


def send_interview_link_email_sync(
    interview_session: models.InterviewSessions,
    db_session: Session,
):
    job_title, candidate_name, candidate_email = get_candidate_details(
        interview_session.application_id, db_session
    )
    link = f"{consts.INTERVIEW_FRONTEND}/requirement-download/prepare/{interview_session.interview_session_id}/"
    seb_join_url = f"{consts.PYTHON_BACKEND_URL}/api/seb/join/{interview_session.interview_session_id}"
    
    exam_exit_password = utils.generate_quit_password()
    hashed_exam_exit_password = hashlib.sha256(exam_exit_password.encode()).hexdigest()
    
    interview_session.exam_exit_password = hashed_exam_exit_password
    db_session.add(interview_session)
    db_session.commit()
    db_session.refresh(interview_session)
    
    

    seb_config_bytes = build_seb_config(interview_session.interview_session_id, link, hashed_exam_exit_password)

    temp_dir = tempfile.gettempdir()
    seb_filename = f"interview_{interview_session.interview_session_id}.seb"
    temp_file_path = os.path.join(temp_dir, seb_filename)

    with open(temp_file_path, "wb") as f:
        f.write(seb_config_bytes)

    try:
        import asyncio

        asyncio.run(
            send_email(
                subject=f"Your Interview Link is Ready: {job_title}",
                template_name="emails/interview_link_ready.html",
                context={
                    "candidate_name": candidate_name,
                    "role": job_title,
                    "seb_join_url": link,
                    "exam_exit_password": exam_exit_password,
                },
                recipients=[candidate_email],
                attachments=[temp_file_path],
            )
        )
        logger.info(f"Interview 30-min reminder with SEB sent to {candidate_email}")

        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

        return True
    except Exception as err:
        logger.error(f"Failed to send 15-min reminder: {err}")
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return False


def send_interview_result_email(
    interview_analysis: models.InterviewAnalysis,
    background_tasks: BackgroundTasks,
    db_session: Session,
):
    job_title, candidate_name, candidate_email = get_candidate_details(
        interview_analysis.application_id, db_session
    )

    cutoff_score = get_cutoff_score(db_session)

    is_selected = interview_analysis.total_score >= cutoff_score

    template = (
        "emails/interview_selected.html"
        if is_selected
        else "emails/interview_rejected.html"
    )

    subject = (
        f"Interview Result - Selected for {job_title}"
        if is_selected
        else f"Interview Result - Update for {job_title}"
    )

    try:
        background_tasks.add_task(
            send_email,
            subject=subject,
            template_name=template,
            context={
                "candidate_name": candidate_name,
                "role": job_title,
                "score": interview_analysis.total_score,
            },
            recipients=[candidate_email],
        )
        logger.info("Interview result email sent")

    except Exception as err:
        logger.error(f"Email sending failed: {err}")

def send_resume_result_email(
    candidate_name: str,
    candidate_email: str,
    job_title: str,
    score: float,
    is_selected: bool,
    background_tasks: BackgroundTasks,
):
    # Only send rejection emails. Resume selected emails are no longer sent.
    if is_selected:
        logger.info(f"Skipping resume selection email for {candidate_email}")
        return

    template = "emails/resume_rejected.html"
    subject = f"Application Update for {job_title}"

    try:
        background_tasks.add_task(
            send_email,
            subject=subject,
            template_name=template,
            context={
                "candidate_name": candidate_name,
                "role": job_title,
                "score": score,
            },
            recipients=[candidate_email],
            attachments=[]
        )
        logger.info("Resume result email scheduled")

    except Exception as err:
        logger.error(f"Resume email failed: {err}")