import time
import logging
from datetime import datetime, timedelta
import pytz
from sqlmodel import Session, select
from app.db.session import engine
from app.models import InterviewSessions
from app.services.email.interview_emails import send_interview_link_email_sync

logger = logging.getLogger(__name__)

def process_scheduled_interviews():
    IST = pytz.timezone('Asia/Kolkata')
    
    logger.info("Starting scheduler worker...")
    while True:
        try:
            with Session(engine) as session:
                pending_interviews = session.exec(
                    select(InterviewSessions).where(
                        InterviewSessions.is_scheduled == True,
                        InterviewSessions.schedule_email_sent == False,
                        InterviewSessions.is_deleted == False
                    )
                ).all()

                now_ist = datetime.now(IST)

                for interview in pending_interviews:
                    if not interview.scheduled_time:
                        continue
                        
                    scheduled_time = interview.scheduled_time
                    if scheduled_time.tzinfo is None:
                        scheduled_time = IST.localize(scheduled_time)
                    else:
                        scheduled_time = scheduled_time.astimezone(IST)

                    send_time = scheduled_time - timedelta(minutes=15)
                    
                    if now_ist >= send_time:
                        logger.info(f"Sending reminder for interview {interview.interview_session_id}")
                        success = send_interview_link_email_sync(interview, session)
                        if success:
                            interview.schedule_email_sent = True
                            session.add(interview)
                            session.commit()
                            
        except Exception as e:
            logger.error(f"Error in process_scheduled_interviews loop: {e}")
            
        time.sleep(60)
