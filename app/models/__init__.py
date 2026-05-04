from typing import Optional, List, Dict, Any
from datetime import datetime, date
from sqlmodel import SQLModel, Field
from sqlalchemy import JSON, Text, Column
from enum import Enum
from app.utils import timezone_utils


class StatusEnum(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"

class InterviewSessionStatusEnum(str, Enum):
    completed = "Completed"
    scheduled = "Scheduled"
    upcoming = "Upcoming"
    did_not_attend = "Did Not Attend"


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


class ResumeAttributes(SQLModel, table=(True)):
    __tablename__ = "tb_resume_attributes"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id")
    analysis_json: str = Field(sa_column=Column(Text))
    custom_attributes: str = Field(default="{}", sa_column=Column(Text))
    analysis_success: bool
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_deleted: bool = Field(default=False)


class ResumeAnalysis(SQLModel, table=(True)):
    __tablename__ = "tb_resume_analysis"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id", unique=True)
    candidate_name: str = Field(max_length=150)
    email: str = Field(max_length=255)
    contact_number: str = Field(max_length=50)
    final_score: float
    skills_match: float
    experience_score: float
    education_score: float
    keywords_match: float
    overall_fit: float
    growth_potential: float
    recommendation_decision: str = Field(max_length=20)
    recommendation_reason: str = Field(sa_column=Column(Text))
    recommendation_confidence: str = Field(max_length=20)
    skill_match_percentage: float
    matching_skills: List[str] = Field(default=[], sa_column=Column(JSON))
    missing_skills: List[str] = Field(default=[], sa_column=Column(JSON))
    experience_level: str = Field(max_length=20)
    matching_experience: List[str] = Field(default=[], sa_column=Column(JSON))
    experience_gaps: List[str] = Field(default=[], sa_column=Column(JSON))
    education_level: str = Field(max_length=20)
    education_highlights: List[str] = Field(default=[], sa_column=Column(JSON))
    matching_education: List[str] = Field(default=[], sa_column=Column(JSON))
    missing_education: List[str] = Field(default=[], sa_column=Column(JSON))
    is_fresher: bool = Field(default=True)
    first_job_start_year: Optional[int] = None
    last_job_end_year: Optional[int] = None
    total_jobs_count: int = Field(default=0)
    average_job_change: Optional[str] = Field(default=None, max_length=50)
    strengths: List[str] = Field(default=[], sa_column=Column(JSON))
    weaknesses: List[str] = Field(default=[], sa_column=Column(JSON))
    red_flags: List[str] = Field(default=[], sa_column=Column(JSON))
    cultural_fit_indicators: List[str] = Field(default=[], sa_column=Column(JSON))
    salary_expectation_alignment: str = Field(max_length=20)
    onboarding_priority: str = Field(max_length=20)
    interview_focus_areas: List[str] = Field(default=[], sa_column=Column(JSON))
    processing_time: float
    processed_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    file_path: str = Field(sa_column=Column(Text))
    file_size: float
    word_count: int
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    status: str = Field(default="Not Shortlisted", max_length=20)
    is_deleted: bool = Field(default=False)
    job_id: int = Field(foreign_key="tb_job_details.job_id")
    email_sent: bool = Field(default=False)


class Jobs(SQLModel, table=True):
    __tablename__ = "tb_jobs"

    job_id: Optional[int] = Field(default=None, primary_key=True)
    job_code: str = Field(max_length=255)
    job_location: str = Field(max_length=255)
    experience: str = Field(max_length=255)
    job_type: str = Field(max_length=255)
    job_info: str = Field(max_length=255)
    job_title: str = Field(max_length=255)
    created_by: str = Field(max_length=255)
    created_date: Optional[datetime] = Field()
    job_level: str = Field(max_length=255)
    job_mode: str = Field(max_length=255)
    job_country: str = Field(max_length=255)


class JobDetails(SQLModel, table=(True)):
    __tablename__ = "tb_job_details"
    id: Optional[int] = Field(default=None, primary_key=True)
    created_by: Optional[str] = Field(max_length=255)
    # job_title: Optional[str] = Field(max_length=255)
    created_date: Optional[datetime] = Field()
    job_description: Optional[str] = Field(sa_column=Column(Text))
    job_id: Optional[int] = Field(default=None, foreign_key="tb_jobs.job_id")
    job_requirements: Optional[str] = Field(sa_column=Column(Text))
    qualification: Optional[str] = Field(max_length=255)
    skills: Optional[str] = Field(sa_column=Column(Text))
    updated_by: Optional[str] = Field(max_length=255)
    updated_date: Optional[datetime] = Field()


class JobApplications(SQLModel, table=(True)):
    __tablename__ = "tb_job_applications"
    id: Optional[int] = Field(default=None, primary_key=True)
    additional_file: Optional[str] = Field(default=None, max_length=255)
    contact_future_opportunities: Optional[bool] = Field()
    cover_letter_description: Optional[str] = Field(default=None, max_length=255)
    created_by: Optional[int] = Field()
    created_date: Optional[datetime] = Field()
    email: Optional[str] = Field(max_length=1000)
    first_name: Optional[str] = Field(max_length=1000)
    job_id: Optional[int] = Field(default=None, foreign_key="tb_jobs.job_id")
    last_name: Optional[str] = Field(max_length=1000)
    ph_no: Optional[str] = Field(max_length=255)
    privacy_policy: Optional[bool] = Field()
    resume: Optional[str] = Field(max_length=255)
    source: Optional[str] = Field(default=None, max_length=255)
    # is_deleted: bool = Field(default=False)


class User(SQLModel, table=(True)):
    __tablename__ = "tb_user"
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(unique=True, foreign_key="tb_candidate_info.id")
    first_name: str = Field(max_length=255)
    last_name: str = Field(max_length=255)
    email: str = Field(unique=True, index=True)
    password: str = Field(unique=True, max_length=255)
    phone_number: str = Field(max_length=255)
    employee_id: str = Field(max_length=255)
    description: str = Field(max_length=255)
    date_of_joining: date = Field()
    alternate_phone_number: str = Field(max_length=255)
    department: str = Field(max_length=255)
    is_first_time_user: bool = Field(default=True)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    last_login: datetime = Field(default_factory=timezone_utils.get_ist_now)
    token: str = Field(max_length=255, nullable=True)
    updated_by: str = Field(max_length=255)
    # is_deleted: bool = Field(default=False)


class ResumeLogs(SQLModel, table=(True)):
    __tablename__ = "tb_resume_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id")
    log_message: str = Field(sa_column=Column(Text))
    status: str = Field(default="INFO", max_length=20)
    component: Optional[str] = Field(default=None, max_length=50)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_deleted: bool = Field(default=False)


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
    status: InterviewSessionStatusEnum = Field(default=InterviewSessionStatusEnum.scheduled, max_length=20)
    is_deleted: bool = Field(default=False)
    exam_exit_password: str = Field(max_length=255)


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
    interview_analysis_date: Optional[datetime] = Field(default=None)
    final_decision: Optional[str] = Field(default="", max_length=20, nullable=True)
    email_sent: bool = Field(default=False)
    is_deleted: bool = Field(default=False)
    job_id: int = Field(foreign_key="tb_job_details.job_id")


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
    is_deleted: bool = Field(default=False)


class InterviewConfiguration(SQLModel, table=(True)):
    __tablename__ = "tb_interview_configuration"
    id: Optional[int] = Field(default=None, primary_key=True)
    configuration_name: str = Field(max_length=255)
    configuration_value: str = Field(max_length=255)


class Skills(SQLModel, table=True):
    __tablename__ = "tb_skills"
    skill_id: Optional[int] = Field(default=None, primary_key=True)
    skill_name: str = Field(max_length=100, unique=True, nullable=False)
    description: Optional[str] = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    # is_deleted: bool = Field(default=False)


class SkillCategories(SQLModel, table=True):
    __tablename__ = "tb_skill_categories"
    category_id: Optional[int] = Field(default=None, primary_key=True)
    category_name: str = Field(max_length=50, nullable=False)


class JobSkillWeightage(SQLModel, table=True):
    __tablename__ = "tb_job_skill_weightage"
    job_skill_id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="tb_jobs.job_id")
    skill_id: int = Field(foreign_key="tb_skills.skill_id")
    category_id: int = Field(foreign_key="tb_skill_categories.category_id")
    experience_level: int
    weightage: int
    # is_deleted: bool = Field(default=False)


class Questions(SQLModel, table=True):
    __tablename__ = "tb_questions"
    question_id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(foreign_key="tb_skills.skill_id")
    question_text: str = Field(sa_column=Column(Text, nullable=False))
    experience_level: int
    question_weightage: int


class InterviewQuestions(SQLModel, table=True):
    __tablename__ = "tb_interview_questions"
    interview_question_id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="tb_jobs.job_id")
    question_id: int = Field(foreign_key="tb_questions.question_id")
    assigned_weightage: int


class ActivityFeed(SQLModel, table=True):
    __tablename__ = "tb_activity_feed"
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=timezone_utils.get_ist_now)
    activity: str = Field(max_length=255)
    # is_deleted: bool = Field(default=False)


class AssetsInfo(SQLModel, table=True):
    __tablename__ = "tb_assets_info"

    asset_id: Optional[int] = Field(default=None, primary_key=True)
    asset_type: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    updated_by: Optional[str] = Field(default=None, max_length=100)
    created_by: Optional[str] = Field(default=None, max_length=100)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    # is_deleted: bool = Field(default=False)


class AssetType(SQLModel, table=True):
    __tablename__ = "tb_asset_type"

    id: Optional[int] = Field(default=None, primary_key=True)
    asset_type: Optional[str] = Field(default=None, max_length=100)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    # is_deleted: bool = Field(default=False)


class EmployeeAssetsInfo(SQLModel, table=True):
    __tablename__ = "tb_employee_assets_info"

    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: Optional[str] = Field(default=None, max_length=255)
    employee_name: Optional[str] = Field(default=None, max_length=255)
    assigned_by: Optional[str] = Field(default=None, max_length=255)
    # created_date: Optional[datetime] = Field(default=None)
    is_deleted: bool = Field(default=False)


class CandidateInfo(SQLModel, table=True):
    __tablename__ = "tb_candidate_info"

    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    phone_number: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=150)
    job_country: Optional[str] = Field(default=None, max_length=100)
    job_title: Optional[str] = Field(default=None, max_length=100)
    job_id: int = Field(foreign_key="tb_jobs.job_id")
    department: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    github_url: Optional[str] = Field(default=None, max_length=255)
    linkedin_url: Optional[str] = Field(default=None, max_length=255)
    application_id: Optional[int] = Field(
        default=None, foreign_key="tb_job_applications.id"
    )
    accepted_date: Optional[datetime]
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    comment: Optional[str] = Field(default=None, sa_column=Column(Text))
    # is_deleted: bool = Field(default=False)


class Offer(SQLModel, table=True):
    __tablename__ = "tb_offer"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Foreign Key → candidate_info.id
    candidate_id: Optional[int] = Field(
        default=None, foreign_key="tb_candidate_info.id"
    )
    offer_letter_path: Optional[str] = Field(default=None, max_length=255)
    ctc: Optional[int]
    issue_date: Optional[datetime]
    accepted_date: Optional[datetime]
    status: Optional[str] = Field(default=None, max_length=50)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    # is_deleted: bool = Field(default=False)


class PreOnBoarding(SQLModel, table=True):
    __tablename__ = "tb_pre_onboarding"

    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    middle_name: Optional[str] = Field(default=None, max_length=100)
    gender: Optional[str] = Field(default=None, max_length=20)
    personal_info: Optional[str] = Field(default=None, sa_column=Column(Text))
    address_info: Optional[str] = Field(default=None, sa_column=Column(Text))
    bank_info: Optional[str] = Field(default=None, sa_column=Column(Text))
    date_of_birth: Optional[str] = Field(default=None, max_length=50)
    nationality: Optional[str] = Field(default=None, max_length=50)
    aadhar_number: Optional[str] = Field(default=None, max_length=20)
    city: Optional[str] = Field(default=None, max_length=100)
    address1: Optional[str] = Field(default=None, max_length=255)
    state: Optional[str] = Field(default=None, max_length=100)
    pincode: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=100)
    bank_account_number: Optional[str] = Field(default=None, max_length=50)
    ifsc_code: Optional[str] = Field(default=None, max_length=20)
    highest_education_qualification: Optional[str] = Field(default=None, max_length=150)
    cgpa: Optional[str] = Field(default=None, max_length=20)
    year: Optional[int]
    is_fresher: Optional[bool]
    education_document: Optional[str] = Field(default=None, max_length=255)
    bank_photo: Optional[str] = Field(default=None, max_length=255)
    aadhar_photo: Optional[str] = Field(default=None, max_length=255)
    pay_slips: Optional[str] = Field(default=None, max_length=255)
    experience: Optional[str] = Field(default=None, sa_column=Column(Text))
    remarks: Optional[str] = Field(default=None, sa_column=Column(Text))
    phone_number: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=150)
    organization_details: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Foreign Key → candidate_info.id
    candidate_id: Optional[int] = Field(
        default=None, foreign_key="tb_candidate_info.id"
    )
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    # is_deleted: bool = Field(default=False)


class BGV(SQLModel, table=True):
    __tablename__ = "tb_bgv"
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor_status: Optional[str] = Field(default=None, max_length=50)
    final_status: Optional[str] = Field(default=None, max_length=50)
    report_url: Optional[str] = Field(default=None, max_length=255)
    # Foreign Key → candidate_info.id
    candidate_id: Optional[int] = Field(
        default=None, foreign_key="tb_candidate_info.id"
    )
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    # is_deleted: bool = Field(default=False)


class RoleRequirement(SQLModel, table=True):
    __tablename__ = "tb_role_requirements"
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="tb_job_details.job_id")
    skill_title: str = Field(max_length=255)
    skill_description: str = Field(sa_column=Column(Text))
    is_mandatory: bool = Field(default=False)
    is_ai_suggested: bool = Field(default=False)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_deleted: bool = Field(default=False)


# class CandidateDecision(SQLModel, table=True):
#     __tablename__ = "tb_candidate_decision"
#     id: Optional[int] = Field(default=None, primary_key=True)
#     application_id: int = Field(foreign_key="tb_job_applications.id")
#     decision: str = Field(max_length=50)
#     comment: str = Field(max_length=255)
#     created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
#     updated_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
#     is_deleted: bool = Field(default=False)
