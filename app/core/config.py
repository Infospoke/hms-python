import os
import json
from dotenv import load_dotenv
from .messages import *
from datetime import datetime
from app.utils import timezone_utils
import logging
from sqlmodel import Session, select
from app import models


logger = logging.getLogger(__name__)

load_dotenv(override=True)


_INTERVIEW_CONFIGS_CACHE = None
import time

_INTERVIEW_CONFIGS_LAST_LOADED = 0
_CACHE_TTL_SECONDS = 60


def refresh_configs_if_needed():
    global _INTERVIEW_CONFIGS_LAST_LOADED
    if time.time() - _INTERVIEW_CONFIGS_LAST_LOADED > _CACHE_TTL_SECONDS:
        _load_interview_configs()


def _load_interview_configs():
    global _INTERVIEW_CONFIGS_CACHE
    global _INTERVIEW_CONFIGS_LAST_LOADED
    from app.db.session import engine

    try:
        with Session(engine) as session:
            interview_configurations = session.exec(
                select(models.InterviewConfiguration)
            ).all()
            _INTERVIEW_CONFIGS_CACHE = {
                config.configuration_name: config.configuration_value
                for config in interview_configurations
            }
            


        logger.debug(
            f"Interview configs loaded from DB: {list(_INTERVIEW_CONFIGS_CACHE.keys())}"
        )
        _INTERVIEW_CONFIGS_LAST_LOADED = time.time()
        _apply_interview_configs()
    except Exception as err:
        logger.error(f"Unable to load interview configs\nError: {str(err)}")
        _INTERVIEW_CONFIGS_CACHE = {}


_AV_CONFIG_KEYS = {
    "KAFKA_AV_TOPIC": str,
    "FFMPEG_PATH": str,
    "MAX_ANSWER_CLIP_BYTES": int,
    "AV_MIN_FACE_COVERAGE": float,
    "AV_MIN_SPEECH_SECONDS": float,
    "AV_MIN_FPS": float,
    "AV_MOUTH_WINDOW_SEC": float,
    "AV_MOUTH_ACTIVITY_THRESHOLD": float,
    "AV_MISMATCH_RATIO_THRESHOLD": float,
    "AV_MULTI_VOICE_MIN_CLUSTERS": int,
    "AV_ENABLE_MULTI_VOICE_FLAG": bool,
    "AV_VOICE_CLUSTER_MIN_SHARE": float,
    "AV_SHADOW_MODE": bool,
    "AV_KEEP_SUSPICIOUS_CLIPS": bool,
    "AV_KEEP_NOT_MEASURABLE_CLIPS": bool,
    "AV_KEEP_ERROR_CLIPS": bool,
}


def _coerce_bool(raw):
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _apply_av_configs(cache):
    """Let every audio/visual proctoring threshold be retuned from the
    tb_interview_configuration table without a redeploy, since none of them
    are calibrated yet and will need to move once real sessions are recorded."""
    for key, caster in _AV_CONFIG_KEYS.items():
        raw = cache.get(key)
        if raw is None:
            continue
        try:
            value = _coerce_bool(raw) if caster is bool else caster(raw)
        except (ValueError, TypeError):
            logger.warning(
                f"{key} value '{raw}' is not a valid {caster.__name__} - keeping previous value."
            )
            continue
        globals()[key] = value


def _apply_interview_configs():
    global _INTERVIEW_CONFIGS_CACHE
    global ENVIRONMENT
    global GOOGLE_API_KEY, GROQ_API_KEY, WHISPER_MODEL_NAME
    global GEMINI_MODEL, GEMINI_MODEL_FOR_AI_INTERVIEWER, GROQ_MODEL, GROQ_MODEL_FOR_JOB_DESCRIPTION
    global AWS_REGION, AWS_ACCESS_KEY, AWS_SECRET_KEY
    global INFOSPOKE_S3_BUCKET_NAME, SQS_ANALYZE_IMAGE_QUEUE_URL, HOST
    global MAX_QUESTION_TIME
    global IMAGE_PROCTORING_TIME_WINDOW
    global RESUME_BATCH_SIZE
    global KAFKA_HOST, KAFKA_GROUP_ID, KAFKA_TOPIC
    global MINIO_HOST, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE
    global DATABASE_URL
    global MAX_QUESTIONS
    global MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, MAIL_PORT, MAIL_SERVER
    global MAIL_STARTTLS, MAIL_SSL_TLS
    global SEB_BROWSER_EXAM_KEY, SEB_QUIT_PASSWORD, DEV_MODE, BASE_URL, PYTHON_BACKEND_URL  # noqa: E501
    global SUPPORTED_FORMATS, SCORING_CONFIG, MAX_SCORE, MIN_SCORE, PASSING_SCORE
    global SCORING_WEIGHTS, THRESHOLDS, CRITICAL_SKILLS_THRESHOLD, MINIMUM_SKILLS_PERCENTAGE
    global SKILLS_VETO_THRESHOLD, EXPERIENCE_COMPENSATION_LIMIT, LISTS, SKIP_KEYWORDS_FOR_CANDIDATE_NAME
    global NON_NAME_WORDS, COMMON_KEYWORDS, SKILL_DATABASE, PROMPTS
    global DEFAULT_PAGE, DEFAULT_LIMIT, DEFAULT_SORT_BY, DEFAULT_SORT_ORDER
    global RAPIDAPI_KEY, JSEARCH_HOST, SALARY_API_HOST

    if not _INTERVIEW_CONFIGS_CACHE:
        logger.warning("_apply_interview_configs called but cache is empty - skipping.")
        return

    cache = _INTERVIEW_CONFIGS_CACHE

    ENVIRONMENT = cache.get("ENVIRONMENT", ENVIRONMENT)
    GOOGLE_API_KEY = cache.get("GOOGLE_API_KEY", GOOGLE_API_KEY)
    GROQ_API_KEY = cache.get("GROQ_API_KEY", GROQ_API_KEY)
    WHISPER_MODEL_NAME = cache.get("WHISPER_MODEL_NAME", WHISPER_MODEL_NAME)
    GEMINI_MODEL = cache.get("GEMINI_MODEL", GEMINI_MODEL)
    GEMINI_MODEL_FOR_AI_INTERVIEWER = cache.get(
        "GEMINI_MODEL_FOR_AI_INTERVIEWER", GEMINI_MODEL_FOR_AI_INTERVIEWER
    )
    GROQ_MODEL = cache.get(
        "GROQ_MODEL", GROQ_MODEL
    )
    GROQ_MODEL_FOR_JOB_DESCRIPTION = cache.get(
        "GROQ_MODEL_FOR_JOB_DESCRIPTION", GROQ_MODEL_FOR_JOB_DESCRIPTION
    )
    AWS_REGION = cache.get("AWS_REGION", AWS_REGION)
    AWS_ACCESS_KEY = cache.get("AWS_ACCESS_KEY", AWS_ACCESS_KEY)
    AWS_SECRET_KEY = cache.get("AWS_SECRET_KEY", AWS_SECRET_KEY)
    INFOSPOKE_S3_BUCKET_NAME = cache.get(
        "INFOSPOKE_S3_BUCKET_NAME", INFOSPOKE_S3_BUCKET_NAME
    )
    SQS_ANALYZE_IMAGE_QUEUE_URL = cache.get(
        "SQS_ANALYZE_IMAGE_QUEUE_URL", SQS_ANALYZE_IMAGE_QUEUE_URL
    )
    HOST = cache.get("HOST", HOST)
    BASE_URL = HOST
    PYTHON_BACKEND_URL = cache.get("PYTHON_BACKEND_URL", PYTHON_BACKEND_URL)
    if not PYTHON_BACKEND_URL:
        PYTHON_BACKEND_URL = BASE_URL

    # DATABASE_URL = cache.get("DATABASE_URL", DATABASE_URL)
    raw_rbs = cache.get("RESUME_BATCH_SIZE")
    if raw_rbs is not None:
        try:
            RESUME_BATCH_SIZE = int(raw_rbs)
        except (ValueError, TypeError):
            logger.warning(
                f"RESUME_BATCH_SIZE value '{raw_rbs}' is not a valid integer - keeping {RESUME_BATCH_SIZE}"
            )

    KAFKA_HOST = cache.get("KAFKA_HOST", KAFKA_HOST)
    KAFKA_GROUP_ID = cache.get("KAFKA_GROUP_ID", KAFKA_GROUP_ID)
    KAFKA_TOPIC = cache.get("KAFKA_TOPIC", KAFKA_TOPIC)

    MINIO_HOST = cache.get("MINIO_HOST", MINIO_HOST)
    MINIO_ACCESS_KEY = cache.get("MINIO_ACCESS_KEY", MINIO_ACCESS_KEY)
    MINIO_SECRET_KEY = cache.get("MINIO_SECRET_KEY", MINIO_SECRET_KEY)
    MINIO_SECURE = str(cache.get("MINIO_SECURE", MINIO_SECURE)).upper() == "TRUE"

    MAIL_USERNAME = cache.get("MAIL_USERNAME", MAIL_USERNAME)
    MAIL_PASSWORD = cache.get("MAIL_PASSWORD", MAIL_PASSWORD)
    MAIL_FROM = cache.get("MAIL_FROM", MAIL_FROM)
    MAIL_PORT = int(cache.get("MAIL_PORT", MAIL_PORT))
    MAIL_SERVER = cache.get("MAIL_SERVER", MAIL_SERVER)
    MAIL_STARTTLS = str(cache.get("MAIL_STARTTLS", MAIL_STARTTLS)).upper() == "TRUE"
    MAIL_SSL_TLS = str(cache.get("MAIL_SSL_TLS", MAIL_SSL_TLS)).upper() == "TRUE"

    raw_mq = cache.get("MAX_QUESTIONS")
    if raw_mq is not None:
        try:
            MAX_QUESTIONS = int(raw_mq)
        except (ValueError, TypeError):
            logger.warning(
                f"MAX_QUESTIONS value '{raw_mq}' is not a valid integer - keeping {MAX_QUESTIONS}"
            )

    SEB_BROWSER_EXAM_KEY = cache.get("SEB_BROWSER_EXAM_KEY", SEB_BROWSER_EXAM_KEY)
    SEB_QUIT_PASSWORD = cache.get("SEB_QUIT_PASSWORD", SEB_QUIT_PASSWORD)
    DEV_MODE = str(cache.get("DEV_MODE", "false")).lower() == "true"

    RAPIDAPI_KEY = cache.get("RAPIDAPI_KEY", RAPIDAPI_KEY)

    if not SEB_BROWSER_EXAM_KEY:
        logger.warning(
            "SEB_BROWSER_EXAM_KEY is empty — SEB hash verification has no security. "
            "Set it in InterviewConfiguration table."
        )
    if not SEB_QUIT_PASSWORD:
        logger.warning(
            "SEB_QUIT_PASSWORD is not set in DB — candidates can quit SEB without a password."
        )
    if DEV_MODE:
        logger.warning(
            "DEV_MODE is ON — SEB verification is disabled. "
            "Do NOT run this in production."
        )

    # Already handled above

    raw_mqt = cache.get("MAX_QUESTION_TIME")
    if raw_mqt is not None:
        try:
            MAX_QUESTION_TIME = int(raw_mqt)
        except (ValueError, TypeError):
            logger.warning(
                f"MAX_QUESTION_TIME value '{raw_mqt}' is not a valid integer - keeping previous value."
            )

    raw_iptw = cache.get("IMAGE_PROCTORING_TIME_WINDOW")
    if raw_iptw is not None:
        try:
            IMAGE_PROCTORING_TIME_WINDOW = int(raw_iptw)
        except (ValueError, TypeError):
            logger.warning(
                f"IMAGE_PROCTORING_TIME_WINDOW value '{raw_iptw}' is not a valid integer - keeping previous value."
            )

    _apply_av_configs(cache)

    global MAIN_SYSTEM_PROMPT, USER_PROMPT
    current_year = str(timezone_utils.get_ist_now().year)
    MAIN_SYSTEM_PROMPT = _get_prompt_content("main_system_prompt", "").replace(
        "__CURRENT_YEAR__", current_year
    )

    logger.debug("Interview config globals applied successfully.")


def _print_all_config():
    logger.info(f"All config: {_INTERVIEW_CONFIGS_CACHE}")


def get_interview_config_value(interview_config_name: str):
    global _INTERVIEW_CONFIGS_CACHE

    if _INTERVIEW_CONFIGS_CACHE is None:
        _load_interview_configs()

    if interview_config_name in _INTERVIEW_CONFIGS_CACHE:
        return _INTERVIEW_CONFIGS_CACHE[interview_config_name]

    raise Exception(f"No config found of name: {interview_config_name}")


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
try:
    with open(CONFIG_PATH, "r") as f:
        CONFIG_DATA = json.load(f)
except FileNotFoundError:
    raise RuntimeError(CONFIG_FILE_NOT_FOUND(CONFIG_PATH))

PROJECT_NAME = CONFIG_DATA.get("project_name", "ATS API")

COMMON_CONFIG = CONFIG_DATA.get("common", {})
ENVIRONMENTS_DATA = CONFIG_DATA.get("environments", {})

ENVIRONMENT = CONFIG_DATA.get("environment", "AWS_DEVELOPMENT")

SUPPORTED_FORMATS = COMMON_CONFIG.get("supported_formats", [".pdf", ".docx", ".doc", ".xlsx"])
SCORING_CONFIG = COMMON_CONFIG.get("scoring", {})
MAX_SCORE = SCORING_CONFIG.get("max_score", 100)
MIN_SCORE = SCORING_CONFIG.get("min_score", 0)
PASSING_SCORE = SCORING_CONFIG.get("passing_score", 60)
SCORING_WEIGHTS = SCORING_CONFIG.get("weights", {})
THRESHOLDS = SCORING_CONFIG.get("thresholds", {})
CRITICAL_SKILLS_THRESHOLD = THRESHOLDS.get("critical_skills", 30)
MINIMUM_SKILLS_PERCENTAGE = THRESHOLDS.get("minimum_skills_percentage", 40)
SKILLS_VETO_THRESHOLD = THRESHOLDS.get("skills_veto", 30)
EXPERIENCE_COMPENSATION_LIMIT = THRESHOLDS.get("experience_compensation_limit", 25)
LISTS = COMMON_CONFIG.get("lists", {})
SKIP_KEYWORDS_FOR_CANDIDATE_NAME = LISTS.get("skip_keywords_for_candidate_name", [])
NON_NAME_WORDS = LISTS.get("non_name_words", [])
COMMON_KEYWORDS = LISTS.get("common_keywords", [])
SKILL_DATABASE = LISTS.get("skill_database", [])
PROMPTS = COMMON_CONFIG.get("prompts", {})
DEFAULT_PAGE = COMMON_CONFIG.get("pagination", {}).get("default_page", 1)
DEFAULT_LIMIT = COMMON_CONFIG.get("pagination", {}).get("default_limit", 10)
DEFAULT_SORT_BY = "processed_at"
DEFAULT_SORT_ORDER = "desc"

DATABASE_URL = ENVIRONMENTS_DATA.get(ENVIRONMENT, {}).get("DATABASE_URL")


GOOGLE_API_KEY: str = None
GROQ_API_KEY: str = None
WHISPER_MODEL_NAME: str = None
GEMINI_MODEL: str = COMMON_CONFIG.get("gemini_model", "gemma-3-27b-it")
GEMINI_MODEL_FOR_AI_INTERVIEWER: str = COMMON_CONFIG.get("gemini_model_for_ai_interviewer", "gemma-3-27b-it")
GROQ_MODEL: str = COMMON_CONFIG.get("groq_model", COMMON_CONFIG.get("groq_model_for_ai_interviewer", "llama-3.3-70b-versatile"))
GROQ_MODEL_FOR_JOB_DESCRIPTION: str = COMMON_CONFIG.get("groq_model_for_job_description", "llama-3.3-70b-versatile")
AWS_REGION: str = None
AWS_ACCESS_KEY: str = None
AWS_SECRET_KEY: str = None
INFOSPOKE_S3_BUCKET_NAME: str = None
SQS_ANALYZE_IMAGE_QUEUE_URL: str = None
HOST: str = None
PORT: str = None
RESUME_BATCH_SIZE: int = COMMON_CONFIG.get("resume_batch_size", 3)

MAX_QUESTION_TIME: int = 60
IMAGE_PROCTORING_TIME_WINDOW: int = 30

KAFKA_HOST: str = None
KAFKA_GROUP_ID: str = None
KAFKA_TOPIC: str = None

# Topic carrying per-answer audio/visual clips for proctoring analysis. Kept
# separate from KAFKA_TOPIC so a backlog of (much larger, much slower) clip
# jobs can never starve live per-frame image proctoring.
KAFKA_AV_TOPIC: str = "av-answer-analysis"

# --- Per-answer audio/visual proctoring ---
# Every threshold below is a starting point, NOT a calibrated value. They must
# be re-derived from real recorded sessions before any of this is shown to a
# recruiter. See AV_SHADOW_MODE.

# Explicit ffmpeg location. Left empty so PATH lookup wins by default; set it
# only on hosts where ffmpeg is installed somewhere non-standard.
FFMPEG_PATH: str = ""

# Largest answer clip accepted by /submit-answer-av.
MAX_ANSWER_CLIP_BYTES: int = 100 * 1024 * 1024

# Minimum share of frames in which a face must be found for the clip to be
# judged at all. Below this the verdict is not_measurable, never suspicious.
AV_MIN_FACE_COVERAGE: float = 0.50

# Minimum seconds of detected speech before a mouth/audio comparison means
# anything. Short answers are not evidence.
AV_MIN_SPEECH_SECONDS: float = 3.0

# Minimum usable video frame rate. Mouth motion cannot be recovered below this.
AV_MIN_FPS: float = 5.0

# Rolling window (seconds) over which mouth-aspect-ratio variation is measured.
AV_MOUTH_WINDOW_SEC: float = 0.40

# A mouth counts as "moving" when the rolling standard deviation of its
# (aspect-corrected) mouth aspect ratio exceeds this. MAR is already normalised
# by mouth width, so this is broadly scale and distance invariant.
#
# Measured on the synthetic fixtures in samples/av: a genuinely still mouth
# sits at a rolling-std of ~0.024 (p90 0.034) purely from landmark jitter,
# while a talking mouth sits at ~0.128 (p25 0.106). An earlier value of 0.015
# was BELOW the still-mouth noise floor, so a motionless mouth read as active
# and the detector missed the very attack it exists to catch.
#
# 0.05 sits above the still-mouth noise and well under talking, leaning toward
# reading a mouth as "moving" (i.e. toward NOT flagging) when uncertain.
# These figures come from a crude drawn face, whose landmarks are noisier than
# a real one's; recalibrate against recorded sessions before trusting a flag.
AV_MOUTH_ACTIVITY_THRESHOLD: float = 0.05

# Flag when the mouth moved during less than this share of detected speech.
AV_MISMATCH_RATIO_THRESHOLD: float = 0.20

# Distinct voice clusters at or above this count flag as multiple speakers.
AV_MULTI_VOICE_MIN_CLUSTERS: int = 2

# Whether the voice-cluster count may raise a `suspicious` verdict on its own.
#
# OFF by default, because the MFCC-clustering implementation is demonstrably
# unreliable: on the synthetic fixtures it reported five clusters for a single
# synthesised voice while reporting one for a clip containing two genuinely
# different voices. Those errors run in both directions, and the
# false-positive direction would mean accusing a candidate who was alone.
#
# The cluster count is still computed and stored on every row, so it can be
# validated against real recordings. Turn this on only once it has been, and
# preferably after replacing the clustering with proper speaker embeddings
# (SpeechBrain ECAPA-TDNN; torch/torchaudio are already installed).
AV_ENABLE_MULTI_VOICE_FLAG: bool = False

# Share of speech windows a cluster must hold to count as a real speaker,
# rather than a burst of noise or a cough.
AV_VOICE_CLUSTER_MIN_SHARE: float = 0.15

# Shadow mode: analyse and store metrics, but write no ProctoringLogs row.
# Turn this on for an initial calibration period.
AV_SHADOW_MODE: bool = False

# Media is kept only when there is something for a human to review. Clean and
# not_measurable clips are deleted as soon as analysis finishes; their metrics
# row survives, so thresholds stay tunable without retaining candidate video.
AV_KEEP_SUSPICIOUS_CLIPS: bool = True
AV_KEEP_NOT_MEASURABLE_CLIPS: bool = False

# Clips whose analysis crashed are kept, because the failure cannot be
# reproduced once the media is gone. This should be a near-empty bucket; if it
# is not, that is the signal to look. Set false to delete these too, accepting
# that production failures become undiagnosable.
AV_KEEP_ERROR_CLIPS: bool = True

MINIO_HOST: str = None
MINIO_ACCESS_KEY: str = None
MINIO_SECRET_KEY: str = None
MINIO_SECURE: bool = None

MAX_QUESTIONS: int = 10

# Dynamic configurations (initialized with types for Pydantic/startup stability)
MAIL_USERNAME: str = ""
MAIL_PASSWORD: str = ""
MAIL_FROM: str = ""
MAIL_PORT: int = 587
MAIL_SERVER: str = ""
MAIL_STARTTLS: bool = True
MAIL_SSL_TLS: bool = False

SEB_BROWSER_EXAM_KEY: str = ""
SEB_QUIT_PASSWORD: str = ""  # Must be set in InterviewConfiguration DB table
DEV_MODE: bool = (
    False  # Set DEV_MODE=true in DB to bypass SEB verification during dev/testing
)
BASE_URL: str = ""
PYTHON_BACKEND_URL: str = ""

RAPIDAPI_KEY: str = ""
JSEARCH_HOST: str = "jsearch.p.rapidapi.com"
SALARY_API_HOST: str = "job-salary-data.p.rapidapi.com"

AI_INTERVIEW_RECOMMENDATION_CRITERIA = ["HIRE", "CONSIDER"]


def _get_prompt_content(key, default=""):
    content = PROMPTS.get(key, default)
    if isinstance(content, list):
        return "\n".join(content)
    return content


current_year = str(timezone_utils.get_ist_now().year)
MAIN_SYSTEM_PROMPT = ""

USER_PROMPT = lambda job_description, resume_text: _get_prompt_content(
    "user_prompt_template", ""
).format(job_description=job_description, resume_text=resume_text)
