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
    question_id: Optional[int] = Field(
        default=None, foreign_key="tb_questions.question_id"
    )
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
    job_id: int = Field(foreign_key="tb_create_job_details.job_id")
