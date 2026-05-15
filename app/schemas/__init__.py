from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.core import config as consts
from app.models import ResumeAnalysis
from enum import Enum


class ResumeBatch(BaseModel):
    batch_id: int
    resume_batch: List[int]


class AnalyseResumesByJobIdRequest(BaseModel):
    job_ids: List[int]


from app.models import ResumeAnalysis


class ResumeAnalysisStats(BaseModel):
    total_resumes: int
    total_analyzed_resumes: int
    average_score: float
    average_processing_time: float
    score_distribution: dict
    hiring_recommendations: dict
    page: int
    total_pages: int


class ResumeAnalysisResponse(BaseModel):
    resume_analysis: Optional[List[Dict[str, Any]]]
    statistics: Optional[ResumeAnalysisStats]


class FilterItem(BaseModel):
    label: str
    checked: bool


class ResumeAnalysisRequest(BaseModel):
    score: Optional[int] = 0
    experience: Optional[List[FilterItem]] = []
    recommendation: Optional[List[FilterItem]] = []
    sort_by: Optional[str] = consts.DEFAULT_SORT_BY
    sort_order: Optional[str] = consts.DEFAULT_SORT_ORDER


class DeleteResumeLogRequest(BaseModel):
    application_id: int


class DeleteResumeLogsRequest(BaseModel):
    application_ids: List[int]


class CreateInterviewSessionRequest(BaseModel):
    application_id: int
    question_type: str = "AI"


class StartInterviewRequest(BaseModel):
    interview_session_id: str


class ScheduleInterviewRequest(BaseModel):
    interview_session_id: str
    scheduled_date: str
    scheduled_time: str


class AdminScheduleInterviewRequest(BaseModel):
    application_id: int
    scheduled_date: str
    scheduled_time: str
    question_type: str = "AI"  # Used when auto-creating a new session


class FetchInterviewAnalysisRequest(BaseModel):
    application_id: int


class UpdateFinalDecisionRequest(BaseModel):
    application_id: int
    decision: str  # "HIRED" or "REJECTED"
    comment: Optional[str] = ""  # Optional note/reason for the decision


class SubmitAnswersRequest(BaseModel):
    interview_session_id: str
    audios: dict


class ProctoringLogRequest(BaseModel):
    interview_session_id: str
    event_type: str
    details: str


class AnalyzeImageRequest(BaseModel):
    interview_session_id: str
    image_base64: str


from pydantic import BaseModel
from typing import List


class DeleteCandidateRequest(BaseModel):
    candidate_ids: List[int]


# --- Test schemas ---


class TestSendInterviewEmailRequest(BaseModel):
    interview_session_id: str


class SkillRequirement(BaseModel):
    skill_title: str


class AISuggestSkillsRequest(BaseModel):
    job_title: str
    department: str
    business_case: str


class AISuggestSkillsResponse(BaseModel):
    success: bool
    skills: List[SkillRequirement]
    message: Optional[str] = None


class SeniorityLevel(str, Enum):
    IC1 = "IC1"
    IC2 = "IC2"
    IC3 = "IC3"
    IC4 = "IC4"
    IC5 = "IC5"
    IC6 = "IC6"
    IC7 = "IC7"
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"
    M5 = "M5"


SENIORITY_TO_YEO = {
    SeniorityLevel.IC1: "0-1",
    SeniorityLevel.IC2: "1-3",
    SeniorityLevel.IC3: "3-5",
    SeniorityLevel.IC4: "5-8",
    SeniorityLevel.IC5: "8-12",
    SeniorityLevel.IC6: "12-15",
    SeniorityLevel.IC7: "15-20",
    SeniorityLevel.M1: "5-8",
    SeniorityLevel.M2: "8-12",
    SeniorityLevel.M3: "12-15",
    SeniorityLevel.M4: "15-20",
    SeniorityLevel.M5: "20+",
}


class GenerateJobDescriptionRequest(BaseModel):
    job_id: Optional[int] = None
    job_title: str = ""
    department: str = ""
    location: str = ""
    seniority_level: str = ""
    num_openings: int = 1
    target_start_date: str = ""
    employment_type: str = "Full-time"
    work_mode: str = ""
    must_have_skills: List[str] = []
    nice_to_have_skills: List[str] = []
    education_requirements: str = ""
    travel_requirement: str = ""
    years_of_experience: str = ""
    required_certifications: List[str] = []
    languages: str = "English"
    old_job_description: Optional[str] = ""
    update_parameter: Optional[str] = ""


class JobDescriptionOutput(BaseModel):
    job_title: str
    job_summary: str
    key_responsibilities: List[str]
    required_qualifications: List[str]
    preferred_qualifications: List[str]
    skills_must_have: List[str]
    skills_nice_to_have: List[str]
    education_requirements: str
    experience_requirements: str
    certifications_required: List[str]
    languages_required: str
    travel_requirement: str
    work_mode: str
    employment_type: str
    location: str
    about_company: str
    job_description_text: str = ""


class GenerateJobDescriptionResponse(BaseModel):
    success: bool
    job_description: Optional[JobDescriptionOutput] = None
    message: Optional[str] = None


class CTCReviewRequest(BaseModel):
    job_title: str
    department: str
    seniority: SeniorityLevel
    location: str
    employment_type: str
    business_justification: str


class SalaryBenchmark(BaseModel):
    source: str
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    median_salary: Optional[float] = None
    currency: Optional[str] = None
    period: Optional[str] = None


class CTCReviewResponse(BaseModel):
    min_salary: float
    max_salary: float


class JobRequirementsRequest(BaseModel):
    job_title: str
    department: str
    seniority: SeniorityLevel
    business_justification: str
    location: str


class ApplicantInfo(BaseModel):
    name: str
    experience: str
    company: str
    score: str
    status: str


class GenerateApplicantsReportRequest(BaseModel):
    job_title: str
    department: str
    location: str
    employment_type: str
    applicants: List[ApplicantInfo]
    report_date: Optional[str] = None


class CertificationSuggestion(BaseModel):
    name: str


class CertificationsResponse(BaseModel):
    certifications: List[CertificationSuggestion]


class LanguageSuggestion(BaseModel):
    language: str


class LanguagesResponse(BaseModel):
    languages: List[LanguageSuggestion]


class QualificationSuggestion(BaseModel):
    degree: str


class QualificationsResponse(BaseModel):
    qualifications: List[QualificationSuggestion]


class CandidateRejectedRequest(BaseModel):
    application_id: int
    rejected: bool


# --- Job Description Revisions ---


class JobDescriptionRevision(BaseModel):
    id: int
    job_id: int
    revision_index: int
    job_description: str
    update_parameter: Optional[str] = None
    created_at: datetime


class JobDescriptionRevisionsResponse(BaseModel):
    job_id: int
    revisions: List[JobDescriptionRevision]
    total_revisions: int
