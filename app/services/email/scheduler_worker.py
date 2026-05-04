import time
import logging
from datetime import datetime, timedelta
import pytz
from sqlmodel import Session, select
from app.db.session import engine
from app import models
from app.services.email.interview_emails import send_interview_link_email_sync

logger = logging.getLogger(__name__)

def process_scheduled_interviews():
    IST = pytz.timezone('Asia/Kolkata')
    
    logger.info("Starting scheduler worker...")
    while True:
        try:
            with Session(engine) as session:
                session.expire_all()
                pending_interviews = session.exec(
                    select(models.InterviewSessions).where(
                        models.InterviewSessions.is_scheduled == True,
                        models.InterviewSessions.schedule_email_sent == False,
                        models.InterviewSessions.is_deleted == False
                    )
                ).all()

                now_ist = datetime.now(IST)

                for interview in pending_interviews:
                    if not interview.scheduled_time:
                        logger.warning(f"Interview {interview.interview_session_id} has no scheduled time.")
                        continue
                        
                    scheduled_time = interview.scheduled_time
                    if scheduled_time.tzinfo is None:
                        scheduled_time = IST.localize(scheduled_time)
                    else:
                        scheduled_time = scheduled_time.astimezone(IST)

                    send_time = scheduled_time - timedelta(minutes=30)
                    no_show_threshold = scheduled_time + timedelta(minutes=30)
                    logger.info(f"Checking interview {interview.interview_session_id}: Scheduled at {scheduled_time}, Send Window starts at {send_time}, No-show at {no_show_threshold}, Current time {now_ist}")
                    
                    # If we are past the 30-minute lead time but NOT yet a no-show
                    if now_ist >= send_time and now_ist < no_show_threshold:
                        if not interview.schedule_email_sent:
                            logger.info(f"Target time reached. Attempting to send link for {interview.interview_session_id}")
                            success = send_interview_link_email_sync(interview, session)

                            if success:
                                try:
                                    interview.schedule_email_sent = True
                                    interview.status = models.InterviewSessionStatusEnum.upcoming
                                    session.add(interview)
                                    session.commit()
                                    session.refresh(interview)
                                    logger.info(f"SUCCESS: Interview {interview.interview_session_id} is now UPCOMING")
                                except Exception as commit_err:
                                    logger.error(f"Failed to commit UPCOMING status for {interview.interview_session_id}: {commit_err}")
                            else:
                                logger.error(f"FAILED to send link email for {interview.interview_session_id}")
                    
                    elif now_ist >= no_show_threshold:
                        logger.info(f"Interview {interview.interview_session_id} (Scheduled: {scheduled_time}) is past the no-show threshold ({no_show_threshold}). Current time: {now_ist}. Marking as Did Not Attend.")
                        if interview.status != models.InterviewSessionStatusEnum.did_not_attend:
                            # Only mark as Did Not Attend if they haven't started
                            from app.models import InterviewAnalysis
                            analysis = session.exec(
                                select(InterviewAnalysis).where(
                                    InterviewAnalysis.interview_session_id == interview.interview_session_id
                                )
                            ).first()
                            
                            if not (analysis and analysis.status in [models.StatusEnum.in_progress, models.StatusEnum.completed]):
                                logger.info(f"Marking interview {interview.interview_session_id} as Did Not Attend")
                                interview.status = models.InterviewSessionStatusEnum.did_not_attend
                                interview.schedule_email_sent = True # Mark as processed
                                session.add(interview)
                                session.commit()
                                session.refresh(interview)
                                logger.info(f"Interview {interview.interview_session_id} finalized as DID NOT ATTEND")

                # Check for "Did Not Attend" (30 mins past scheduled time)
                expired_interviews = session.exec(
                    select(models.InterviewSessions).where(
                        models.InterviewSessions.is_scheduled == True,
                        models.InterviewSessions.is_deleted == False,
                        models.InterviewSessions.status.in_([
                            models.InterviewSessionStatusEnum.scheduled,
                            models.InterviewSessionStatusEnum.upcoming
                        ])
                    )
                ).all()

                for interview in expired_interviews:
                    if not interview.scheduled_time:
                        continue
                    
                    sched_time = interview.scheduled_time
                    if sched_time.tzinfo is None:
                        sched_time = IST.localize(sched_time)
                    else:
                        sched_time = sched_time.astimezone(IST)
                    
                    if now_ist > (sched_time + timedelta(minutes=30)):
                        # Check if they actually started the interview by looking at InterviewAnalysis
                        from app.models import InterviewAnalysis
                        analysis = session.exec(
                            select(InterviewAnalysis).where(
                                InterviewAnalysis.interview_session_id == interview.interview_session_id
                            )
                        ).first()
                        
                        # Only mark as Did Not Attend if they haven't started (status not in_progress/completed)
                        if not (analysis and analysis.status in [models.StatusEnum.in_progress, models.StatusEnum.completed]):
                            logger.info(f"Marking interview {interview.interview_session_id} as Did Not Attend")
                            interview.status = models.InterviewSessionStatusEnum.did_not_attend
                            session.add(interview)
                session.commit()
                            
        except Exception as e:
            logger.error(f"Error in process_scheduled_interviews loop: {e}")
            
        time.sleep(60)
