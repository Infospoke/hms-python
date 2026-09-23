from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import JSON, Text, Column
from enum import Enum
from app.utils import timezone_utils


# --- Enum Definitions ---
class StatusEnum(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"


class InterviewSessionStatusEnum(str, Enum):
    Screened = "Screened"
    completed = "completed"
    scheduled = "scheduled"
    upcoming = "upcoming"
    did_not_attend = "did not attend"


class ProctoringEventType(str, Enum):
    visual_violation = "Visual Violation"
    browser_tab_switch = "BROWSER_TAB_SWITCH"
    right_click_blocked = "RIGHT_CLICK_BLOCKED"
    fullscreen_exit = "FULLSCREEN_EXIT"
    fullscreen_auto_reenter = "FULLSCREEN_AUTO_REENTER"
    esc_key_attempt = "ESC_KEY_ATTEMPT"
    forbidden_key_attempt = "FORBIDDEN_KEY_ATTEMPT"
    clipboard_violation = "Clipboard Violation"
    default = "No Violation"
    candidate_picture = "CANDIDATE_PICTURE"
    av_mouth_mismatch = "Lip Sync Mismatch"
    multiple_voices = "MULTIPLE VOICES"


class AVVerdictEnum(str, Enum):
    """Outcome of per-answer audio/visual analysis.

    `not_measurable` is deliberately NOT a kind of suspicion: it means the clip
    could not be judged (face not visible enough, too little speech, decode
    failure). Treating it as a violation would push false positives onto
    candidates with poor lighting or cheap webcams, so it is kept separate.
    """

    clean = "clean"
    suspicious = "suspicious"
    not_measurable = "not_measurable"
    error = "error"


# --- Model Definitions ---
class InterviewSessions(SQLModel, table=(True)):
    __tablename__ = "tb_interview_sessions"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id")
    interview_session_id: str = Field(max_length=255, unique=True, nullable=False)
    question_type: str = Field(default="AI", max_length=20)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    scheduled_time: Optional[datetime] = Field(default=None)
    is_scheduled: bool = Field(default=False)
    schedule_email_sent: bool = Field(default=False)
    status: Optional[InterviewSessionStatusEnum] = Field(
        default=None, max_length=20, nullable=True
    )
    is_deleted: bool = Field(default=False)
    exam_exit_password: str = Field(max_length=255)
    interview_scheduled_datetime: Optional[datetime] = Field(default=None)
    job_id: int = Field(foreign_key="tb_create_job_details.job_id")
    min_pass_percentage: Optional[int] = Field(default=None)
    acceptable_score_range: Optional[str] = Field(default=None, max_length=50)
    questions_status: bool = Field(default=False)
    move_to_schedule: bool = Field(default=False)
    move_to_schedule_datetime: Optional[datetime] = Field(default=None)
    scheduled_by: Optional[str] = Field(default=None, max_length=50)
    interview_link: str = Field(max_length=500)




class InterviewAnalysis(SQLModel, table=(True)):
    __tablename__ = "tb_interview_analysis"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id")
    interview_session_id: str = Field(
        foreign_key="tb_interview_sessions.interview_session_id"
    )
    status: StatusEnum = Field(default=StatusEnum.not_started)
    questions: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    total_score: float = Field(default=0.0)
    recommendation: str = Field(max_length=20, nullable=True)
    analysis_completed: bool = Field(default=False)
    final_decision: Optional[str] = Field(default="", max_length=20, nullable=True)
    email_sent: bool = Field(default=False)
    is_deleted: bool = Field(default=False)
    job_id: int = Field(foreign_key="tb_create_job_details.job_id")
    interview_analysis_date: Optional[datetime] = Field(default=None)
    interview_started_datetime: Optional[datetime] = Field(default=None)


class QNA_Analysis(SQLModel, table=(True)):
    __tablename__ = "tb_qna_analysis"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: Optional[int] = Field(
        default=None, foreign_key="tb_job_applications.id"
    )
    interview_analysis_id: int = Field(foreign_key="tb_interview_analysis.id")
    question_id: Optional[int] = Field(default=None)
    question_text: str = Field(sa_column=Column(Text))
    answer_text: str = Field(sa_column=Column(Text))
    ai_analysis: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_deleted: bool = Field(default=False)


class ProctoringLogs(SQLModel, table=(True)):
    __tablename__ = "tb_proctoring_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    interview_analysis_id: int = Field(foreign_key="tb_interview_analysis.id")
    event_type: str = Field(default=ProctoringEventType.default)
    timestamp: datetime = Field(default_factory=timezone_utils.get_ist_now)
    details: Optional[str] = Field(default=None, sa_column=Column(Text))
    image_path: Optional[str] = Field(default=None)
    tb_severity: Optional[str] = Field(default="low severity", max_length=20)
    is_deleted: bool = Field(default=False)


class AnswerAVAnalysis(SQLModel, table=(True)):
    """Per-answer audio/visual proctoring metrics.

    One row per submitted answer clip. The row is written for EVERY analysed
    clip, including clean ones whose media is deleted straight afterwards, so
    thresholds can be tuned later from the metrics even when the clip is gone.
    """

    __tablename__ = "tb_answer_av_analysis"
    id: Optional[int] = Field(default=None, primary_key=True)
    interview_analysis_id: int = Field(foreign_key="tb_interview_analysis.id")
    interview_session_id: str = Field(max_length=255, index=True)
    question_index: int

    # MinIO key, cleared once a clean clip is deleted after processing.
    clip_path: Optional[str] = Field(default=None, max_length=500)
    clip_retained: bool = Field(default=False)

    verdict: str = Field(default=AVVerdictEnum.error, max_length=20)
    reasons: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    duration_sec: float = Field(default=0.0)
    video_fps: float = Field(default=0.0)
    frame_count: int = Field(default=0)
    frames_with_face: int = Field(default=0)
    face_coverage: float = Field(default=0.0)

    speech_seconds: float = Field(default=0.0)
    speech_ratio: float = Field(default=0.0)
    distinct_voice_clusters: int = Field(default=0)

    # The headline signal: of the time the microphone was capturing speech,
    # what fraction did the visible mouth actually move?
    mouth_active_ratio_during_speech: float = Field(default=0.0)
    mouth_active_ratio_during_silence: float = Field(default=0.0)
    mouth_active_ratio_overall: float = Field(default=0.0)

    metrics: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_deleted: bool = Field(default=False)


class InterviewConfiguration(SQLModel, table=(True)):
    __tablename__ = "tb_interview_configuration"
    id: Optional[int] = Field(default=None, primary_key=True)
    configuration_name: str = Field(max_length=255)
    configuration_value: str = Field(max_length=255)


class AIInterviewQuestions(SQLModel, table=(True)):
    __tablename__ = "tb_ai_interview_questions"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id")
    number_of_questions: int
    difficulty_level: str = Field(max_length=50)
    question_type: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    questions: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    # job_id: int = Field(foreign_key="tb_create_job_details.job_id")

class EvaluationSummary(SQLModel, table=True):
    __tablename__ = "tb_interview_evaluation_summary"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id")
    candidate_name: Optional[str] = Field(default=None, max_length=255)
    candidate_email: Optional[str] = Field(default=None, max_length=255)
    total_rounds_completed: Optional[int] = Field(default=None)
    total_rounds: Optional[int] = Field(default=None)
    total_questions_count: Optional[int] = Field(default=None)
    average_score_across_rounds: Optional[float] = Field(default=None)
    status: Optional[str] = Field(default=None, max_length=255)
    rounds_performance: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    consolidated_evaluation: Optional[Dict[str, Any]] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    technical_score: Optional[float] = Field(default=None)
    managerial_score: Optional[float] = Field(default=None)
    hr_score: Optional[float] = Field(default=None)
    ai_score: Optional[float] = Field(default=None)
    ai_recommendation_status: Optional[str] = Field(default=None, max_length=255)
    total_questions_count: Optional[int] = Field(default=None)
    attempted_questions_count: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
