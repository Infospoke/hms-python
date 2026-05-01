import os
import sys
import warnings

os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"
os.environ["TF_CPP_VMODULE"] = "inference_feedback_manager=0"
os.environ["ABSL_MIN_LOG_LEVEL"] = "3"
os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"
warnings.filterwarnings("ignore", category=Warning)

import uvicorn
import logging
import subprocess
import atexit

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s: %(message)s")

if __name__ == "__main__":
    from app.db.session import engine, create_db_and_tables
    from app.core.config import _load_interview_configs

    logging.info("Initializing database...")
    create_db_and_tables()

    logging.info("Loading configurations from database...")
    _load_interview_configs()
    logging.info("Starting background workers as a separate process...")
    worker_process = subprocess.Popen(
        [sys.executable, "-u", "run_workers.py"], stdout=sys.stdout, stderr=sys.stderr
    )

    def cleanup():
        logging.info("Terminating background workers...")
        worker_process.terminate()
        worker_process.wait()

    atexit.register(cleanup)

    logging.info("Starting FastAPI server with HTTP workers...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=5002, workers=1, reload=False)
