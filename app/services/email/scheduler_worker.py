import time
import logging
from datetime import datetime, timedelta
import pytz
from sqlalchemy import func
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
                # Get all interviews that are scheduled and not deleted
                active_interviews = session.exec(
                    select(models.InterviewSessions).where(
                        models.InterviewSessions.is_scheduled == True,
                        models.InterviewSessions.is_deleted == False,
                        models.InterviewSessions.status.in_([
                            models.InterviewSessionStatusEnum.scheduled,
                            models.InterviewSessionStatusEnum.upcoming,
                            "scheduled",
                            "upcoming"
                        ])
                    )
                ).all()

                now_ist = datetime.now(IST)

                for interview in active_interviews:
                    if not interview.scheduled_time:
                        continue
                        
                    # 1. Deduplicated Timezone Logic
                    sched_time = interview.scheduled_time
                    if sched_time.tzinfo is None:
                        sched_time = IST.localize(sched_time)
                    else:
                        sched_time = sched_time.astimezone(IST)

                    send_time = sched_time - timedelta(minutes=15)
                    no_show_threshold = sched_time + timedelta(minutes=15)
                    
                    # 2. Logic for Sending Link (Upcoming)
                    if not interview.schedule_email_sent and now_ist >= send_time and now_ist < no_show_threshold:
                        logger.info(f"Target time reached. Sending link for {interview.interview_session_id}")
                        if send_interview_link_email_sync(interview, session):
                            interview.schedule_email_sent = True
                            interview.status = models.InterviewSessionStatusEnum.upcoming
                            session.add(interview)
                    
                    # 3. Logic for Expiration (Did Not Attend)
                    elif now_ist >= no_show_threshold:
                        from app.models import InterviewAnalysis, QNA_Analysis
                        analysis = session.exec(
                            select(InterviewAnalysis).where(
                                InterviewAnalysis.interview_session_id == interview.interview_session_id
                            )
                        ).first()
                        
                        # Check if questions have been generated
                        questions_exist = False
                        if analysis:
                            q_count = session.exec(select(func.count(QNA_Analysis.id)).where(QNA_Analysis.interview_analysis_id == analysis.id)).one()
                            questions_exist = q_count > 0

                        # Mark as Did Not Attend ONLY if no questions are generated 
                        if not questions_exist and not (analysis and analysis.status in [models.StatusEnum.in_progress, models.StatusEnum.completed]):
                            logger.info(f"Marking {interview.interview_session_id} as Did Not Attend")
                            logger.info(f"Marking {interview.interview_session_id} as Did Not Attend. Using literal string: 'did not attend'")
                            interview.status = "did not attend"
                            session.add(interview)

                session.commit()
                            
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}")
            
        time.sleep(60)
