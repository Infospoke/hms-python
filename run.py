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
import logging.handlers
import subprocess
import atexit
import threading
import certifi

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FORMAT = "%(name)s - %(levelname)s: %(message)s"


def _configure_logging():
    """Console logging that cannot silently drop records, plus a file copy.

    The Windows console defaults to cp1252. Any non-ASCII in a log message -
    a transcript, a candidate's name, a curly quote in a question - raised
    UnicodeEncodeError inside the handler, which printed "--- Logging error ---"
    and THREW THE RECORD AWAY. The messages most likely to contain non-ASCII
    were the ones carrying answers and exception text, so precisely the useful
    logs were the ones being lost.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, "app.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
            errors="replace",
        )
        handlers.append(file_handler)
    except Exception as e:  # logging must never stop the app from starting
        print(f"Could not open log file, continuing with console only: {e}")

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers)


_configure_logging()

if __name__ == "__main__":

    os.environ["SSL_CERT_FILE"] = certifi.where()
    from app.db.session import engine, create_db_and_tables
    from app.core.config import _load_interview_configs

    logging.info("Initializing database...")
    create_db_and_tables()

    logging.info("Loading configurations from database...")
    _load_interview_configs()
    logging.info("Starting background workers as a separate process...")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workers_path = os.path.join(current_dir, "run_workers.py")

    # The workers used to inherit this process's stdout handle directly, so two
    # processes wrote to the same console concurrently and shredded each
    # other's lines. Their output is piped here instead and relayed one whole
    # line at a time, tagged so it is obvious which process emitted it.
    worker_env = os.environ.copy()
    worker_env["PYTHONUTF8"] = "1"
    worker_env["PYTHONIOENCODING"] = "utf-8:replace"

    worker_process = subprocess.Popen(
        [sys.executable, "-u", workers_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=worker_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    def _relay_worker_output():
        worker_log = None
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            worker_log = open(
                os.path.join(LOG_DIR, "workers.log"),
                "a",
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            pass
        try:
            for line in worker_process.stdout:
                line = line.rstrip("\n")
                # One write per line keeps it atomic against uvicorn's output.
                sys.stdout.write(f"[workers] {line}\n")
                sys.stdout.flush()
                if worker_log:
                    worker_log.write(line + "\n")
                    worker_log.flush()
        except Exception as e:
            print(f"[workers] output relay stopped: {e}")
        finally:
            if worker_log:
                try:
                    worker_log.close()
                except Exception:
                    pass

    threading.Thread(
        target=_relay_worker_output, daemon=True, name="worker-log-relay"
    ).start()

    def cleanup():
        logging.info("Terminating background workers...")
        worker_process.terminate()
        worker_process.wait()

    atexit.register(cleanup)

    logging.info("Starting FastAPI server with HTTP workers...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=5002, workers=1, reload=False)