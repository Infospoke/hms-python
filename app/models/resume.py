from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import JSON, Text, Column
from app.utils import timezone_utils

# --- Model Definitions ---

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

class ResumeLogs(SQLModel, table=(True)):
    __tablename__ = "tb_resume_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="tb_job_applications.id")
    log_message: str = Field(sa_column=Column(Text))
    status: str = Field(default="INFO", max_length=20)
    component: Optional[str] = Field(default=None, max_length=50)
    created_date: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_deleted: bool = Field(default=False)


class ResumeAnalysisUpdate(SQLModel, table=True):
    __tablename__ = "tb_applicant_details"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int
    application_id: int = Field(foreign_key="tb_job_applications.id", unique=True)
    name: Optional[str] = Field(default=None, max_length=255)
    designation: Optional[str] = Field(default=None, sa_column=Column(Text))
    current_location: Optional[str] = Field(default=None, max_length=255)
    total_experience: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    notice_period: Optional[str] = Field(default=None, max_length=255)
    phone_no: Optional[str] = Field(default=None, max_length=255)
    current_company: Optional[str] = Field(default=None, sa_column=Column(Text))

    personal_date_of_birth: Optional[str] = Field(default=None, max_length=100)
    personal_gender: Optional[str] = Field(default=None, max_length=50)
    personal_nationality: Optional[str] = Field(default=None, max_length=100)
    personal_languages_known: List[str] = Field(default=[], sa_column=Column(JSON))
    personal_address: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    education_details: List[dict] = Field(default=[], sa_column=Column(JSON))
    experience_details: List[dict] = Field(default=[], sa_column=Column(JSON))
    time_line: List[str] = Field(default=[], sa_column=Column(JSON))
    company_details: List[str] = Field(default=[], sa_column=Column(JSON))
    list_of_experience: List[str] = Field(default=[], sa_column=Column(JSON))
    projects: List[dict] = Field(default=[], sa_column=Column(JSON))
    certifications: List[str] = Field(default=[], sa_column=Column(JSON))
    total_projects_count: int = Field(default=0)

    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    updated_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_deleted: bool = Field(default=False)