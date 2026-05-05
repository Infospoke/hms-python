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