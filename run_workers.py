import os
import sys
import threading
import time
import logging

os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"
from app.services import analyze_image_worker
from app.services.ai_interviewer.analysis_worker import AnalysisWorker
from app.core import config as consts
from app.db.session import create_db_and_tables

if os.path.exists("logging.conf"):
    logging.config.fileConfig("logging.conf", disable_existing_loggers=False)
else:
    logging.basicConfig(
        level=logging.INFO, format="%(name)s - %(levelname)s: %(message)s"
    )

logger = logging.getLogger(__name__)


def main():
    logger.info("Starting up independent background workers...")

    create_db_and_tables()
    consts._load_interview_configs()

    logger.info("Preloading proctoring models...")
    from app.services.ai_interviewer.proctoring import ProctoringEngine

    ProctoringEngine()
    logger.info("Proctoring models preloaded successfully.")

    image_thread = threading.Thread(
        target=analyze_image_worker.run_worker,
        daemon=True,
        name="analyze-image-worker",
    )
    image_thread.start()
    logger.info("analyze_image_worker: thread started.")

    analysis_worker = AnalysisWorker()
    analysis_worker.start()
    logger.info("AnalysisWorker: thread started.")

    from app.services.email.scheduler_worker import process_scheduled_interviews
    scheduler_thread = threading.Thread(
        target=process_scheduled_interviews,
        daemon=True,
        name="scheduler-worker",
    )
    scheduler_thread.start()
    logger.info("scheduler_worker: thread started.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down background workers gracefully...")
        sys.exit(0)


if __name__ == "__main__":
    main()
