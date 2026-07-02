from typing import Optional, List
from datetime import datetime, date
from sqlmodel import SQLModel, Field
from sqlalchemy import Text, Column, String
from app.utils import timezone_utils
from sqlalchemy.dialects.postgresql import ARRAY, JSON


# --- Model Definitions ---

class CreateJobDetails(SQLModel, table=True):
    __tablename__ = "tb_create_job_details"

    job_id: Optional[int] = Field(default=None, primary_key=True)
    job_title: Optional[str] = None
    role_id: Optional[int] = Field(default=None, alias="role_Id")
    business_unit: Optional[int] = Field(default=None)
    department: Optional[int] = Field(default=None)
    location: Optional[str] = None
    country: Optional[str] = None
    job_code: Optional[str] = Field(default=None, unique=True)
    openings: Optional[int] = None
    target_start_date: Optional[date] = None
    work_mode: Optional[str] = None
    employment_type: Optional[str] = None
    skills_must_have: Optional[str] = Field(default=None,sa_column=Column(Text))
    nice_to_have_skills: Optional[str] = Field(default=None,sa_column=Column(Text))
    min_experience: Optional[int] = None
    max_experience: Optional[int] = None
    additional_notes: Optional[str] = Field(default=None,sa_column=Column(Text))
    submit: bool = Field(default=False)
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=timezone_utils.get_ist_now)
    is_open: Optional[bool] = None
    education_requirements: Optional[str] = None
    sr_id: Optional[str] = None
    certifications_required: Optional[str] = Field(default=None,sa_column=Column(Text))
    languages: Optional[str] = None
    plan_id: Optional[int] = None

class JobDescription(SQLModel, table=True):
    __tablename__ = "tb_job_description"

    id: Optional[int] = Field(default=None, primary_key=True)
    sr_id: Optional[str] = None
    job_id: Optional[int] = None
    description: Optional[List[dict]] = Field(default=None,sa_column=Column(JSON))
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
    job_id: Optional[int] = Field(default=None, foreign_key="tb_create_job_details.job_id")
    last_name: Optional[str] = Field(max_length=1000)
    ph_no: Optional[str] = Field(max_length=255)
    privacy_policy: Optional[bool] = Field()
    resume: Optional[str] = Field(max_length=255)
    source: Optional[str] = Field(default=None, max_length=255)
    rejected: Optional[bool] = Field(default=False)
    stage_entry_date: Optional[datetime] = Field(default=None)
    current_stage: Optional[str] = Field(default=None, max_length=255)
    in_person_interviews: Optional[bool] = Field(default=False)
    # is_deleted: bool = Field(default=False)


class User(SQLModel, table=True):
    __tablename__ = "tb_user"

    id: Optional[int] = Field(default=None, primary_key=True)

    active: bool
    deactivated: bool

    business_unit_id: int
    department_id: int
    employment_type_id: int
    user_type_id: int
    user_id: int
    employee_id: int

    email: str = Field(max_length=255)
    first_name: str = Field(max_length=50)
    last_name: str = Field(max_length=50)

    mobile_number: str = Field(max_length=15)
    alternate_contact: Optional[str] = Field(default=None, max_length=15)

    username: Optional[str] = Field(default=None, max_length=255)

    password: Optional[str] = Field(default=None, max_length=255)
    pin: Optional[str] = Field(default=None, max_length=255)

    role_name: Optional[str] = Field(default=None, max_length=255)
    role_id: Optional[int] = None

    updated_at: Optional[date] = None
    updated_by: Optional[str] = Field(default=None, max_length=255)

    account_locked: Optional[bool] = None
    failed_attempts: Optional[int] = None
    force_password_reset: Optional[bool] = None

    lock_time: Optional[datetime] = None
    password_updated_at: Optional[datetime] = None
    pin_updated_at: Optional[datetime] = None

    first_time_login: Optional[bool] = None
    first_time_mobile_login: Optional[bool] = None
    first_time_web_login: Optional[bool] = None

    candidate_id: Optional[int] = None


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
    job_id: int = Field(foreign_key="tb_create_job_details.job_id")
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
    job_id: int = Field(foreign_key="tb_create_job_details.job_id")
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
    job_id: int = Field(foreign_key="tb_create_job_details.job_id")
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
    # comment: Optional[str] = Field(default=None, sa_column=Column(Text))
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

# --- NEW TABLES ---

from enum import Enum


class AssignRoles(SQLModel, table=True):
    __tablename__ = "tb_assign_roles"

    id: Optional[int] = Field(default=None, primary_key=True)

    assign_role_id: int
    role_id: int
    user_id: int

    assigned_at: Optional[date] = None
    assigned_by: Optional[str] = Field(default=None, max_length=255)


class BudgetCompensation(SQLModel, table=True):
    __tablename__ = "tb_budget_compensation"

    id: Optional[int] = Field(default=None, primary_key=True)

    annual_hiring_cost: Optional[int] = None  # bigint
    approved: Optional[bool] = None
    equity: Optional[bool] = None
    equity_amount: Optional[int] = None

    proposed_total_compensation: Optional[int] = None

    relocation_budget: Optional[bool] = None
    relocation_budget_amount: Optional[int] = None

    signing_bonus: Optional[bool] = None
    signing_bonus_amount: Optional[int] = None

    sr_id: Optional[str] = Field(default=None, max_length=255)

    submitted: Optional[bool] = None

    budget_compensation_status: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = Field(default=None, max_length=255)

    maximum_salary: Optional[int] = None  # bigint
    minimum_salary: Optional[int] = None  # bigint


class BusinessUnit(SQLModel, table=True):
    __tablename__ = "tb_business_unit"

    id: Optional[int] = Field(default=None, primary_key=True)

    business_id: Optional[int] = None
    business_name: Optional[str] = Field(default=None, max_length=255)


class ChildReportingManagerInfo(SQLModel, table=True):
    __tablename__ = "tb_child_reporting_manager_info"

    staffing_requisition_id: int = Field(primary_key=True)

    reporting_manager_ids: Optional[int] = None


class Departments(SQLModel, table=True):
    __tablename__ = "tb_departments"

    id: Optional[int] = Field(default=None, primary_key=True)

    business_unit_id: Optional[int] = None
    department_id: Optional[int] = None

    department_name: Optional[str] = Field(default=None, max_length=255)
    dept_code: Optional[str] = Field(default=None, max_length=255)


class EmploymentType(SQLModel, table=True):
    __tablename__ = "tb_employement_type"

    id: Optional[int] = Field(default=None, primary_key=True)

    employment_id: Optional[int] = None
    employement_type: Optional[str] = Field(default=None, max_length=255)


class Module(SQLModel, table=True):
    __tablename__ = "tb_module"

    id: Optional[int] = Field(default=None, primary_key=True)

    created_by: Optional[str] = Field(default=None, max_length=255)
    created_date: Optional[date] = None

    module_id: int
    module_name: Optional[str] = Field(default=None, max_length=255)

    parent_id: int

    updated_by: Optional[str] = Field(default=None, max_length=255)
    updated_date: Optional[date] = None


class CredentialType(str, Enum):
    PASSWORD = "PASSWORD"
    PIN = "PIN"


class PasswordHistory(SQLModel, table=True):
    __tablename__ = "tb_password_history"

    id: Optional[int] = Field(default=None, primary_key=True)

    created_at: Optional[datetime] = None

    credential: str = Field(max_length=255)
    credential_type: CredentialType

    user_id: int


class Permission(SQLModel, table=True):
    __tablename__ = "tb_permission"

    id: Optional[int] = Field(default=None, primary_key=True)

    can_create: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_view: Optional[bool] = None
    can_export: Optional[bool] = None

    created_by: Optional[str] = Field(default=None, max_length=255)
    created_date: Optional[date] = None

    updated_by: Optional[str] = Field(default=None, max_length=255)
    updated_date: Optional[date] = None

    module_id: int
    permission_id: int
    role_id: int


class Role(SQLModel, table=True):
    __tablename__ = "tb_role"

    id: Optional[int] = Field(default=None, primary_key=True)

    business_unit_id: Optional[int] = None
    department_id: Optional[int] = None

    role_id: int
    role_name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=255)

    created_by: Optional[str] = Field(default=None, max_length=255)
    created_date: Optional[date] = None

    updated_by: Optional[str] = Field(default=None, max_length=255)
    updated_date: Optional[date] = None


class RolesRequirements(SQLModel, table=True):
    __tablename__ = "tb_roles_requirements"

    id: Optional[int] = Field(default=None, primary_key=True)

    approved: Optional[bool] = None
    assessment_required: Optional[bool] = None

    certifications_required: Optional[str] = Field(default=None, max_length=1000)
    education_requirements: Optional[str] = Field(default=None, max_length=255)
    languages: Optional[str] = Field(default=None, max_length=255)

    max_experience: Optional[int] = None
    min_experience: Optional[int] = None

    max_interviews: Optional[int] = None
    min_interviews: Optional[int] = None

    nice_to_have_skills: Optional[str] = Field(default=None, max_length=1000)
    skills_must_have: Optional[str] = Field(default=None, max_length=1000)

    sr_id: str = Field(max_length=255)

    submitted: Optional[bool] = None

    travel_requirements: Optional[str] = Field(default=None, max_length=255)


class SeniorityLevel(SQLModel, table=True):
    __tablename__ = "tb_seniority_level"

    id: Optional[int] = Field(default=None, primary_key=True)

    seniority_level: Optional[str] = Field(default=None, max_length=255)


class SrBusinessJustification(SQLModel, table=True):
    __tablename__ = "tb_sr_business_justification"

    id: Optional[int] = Field(default=None, primary_key=True)

    approved: Optional[bool] = None
    business_case: Optional[str] = Field(default=None, max_length=2000)
    document: Optional[str] = Field(default=None, max_length=255)
    impact_if_not_filled: Optional[str] = Field(default=None, max_length=2000)

    replaces_employee: Optional[int] = None
    requisition_type: Optional[str] = Field(default=None, max_length=255)

    sr_id: str = Field(max_length=255)

    submitted: Optional[bool] = None


class SrPositionBasics(SQLModel, table=True):
    __tablename__ = "tb_sr_position_basics"

    id: Optional[int] = Field(default=None, primary_key=True)

    approved: Optional[bool] = None

    business_unit: Optional[int] = None
    department: Optional[int] = None
    seniority_level: Optional[int] = None

    created_by: Optional[str] = Field(default=None, max_length=255)
    created_on: Optional[date] = None

    employment_type: Optional[str] = Field(default=None, max_length=255)
    job_title: Optional[str] = Field(default=None, max_length=255)
    location: Optional[str] = Field(default=None, max_length=255)

    openings: Optional[int] = None
    priority: Optional[str] = Field(default=None, max_length=255)

    sr_id: Optional[str] = Field(default=None, max_length=255)

    submitted: Optional[bool] = None
    target_start_date: Optional[date] = None

    work_mode: Optional[str] = Field(default=None, max_length=255)

class TravelRequirement(SQLModel, table=True):
    __tablename__ = "tb_travel_requirement"

    id: Optional[int] = Field(default=None, primary_key=True)

    travel_requirement: Optional[str] = Field(default=None, max_length=255)


class UserType(SQLModel, table=True):
    __tablename__ = "tb_user_type"

    id: Optional[int] = Field(default=None, primary_key=True)

    user_type: Optional[str] = Field(default=None, max_length=255)
    user_type_id: Optional[int] = None


class InterviewPlan(SQLModel, table=True):
    __tablename__ = "tb_interview_plan"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: Optional[int] = Field(default=None)
    plan_id: Optional[int] = Field(default=None)
    sr_id: Optional[str] = Field(default=None, max_length=255)
    user_id: Optional[int] = Field(default=None)
    role_name: Optional[str] = Field(default=None, max_length=255)
    plan_name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: Optional[str] = Field(default=None, max_length=255)
    approval_status: Optional[str] = Field(default=None, max_length=255)
    created_by: Optional[str] = Field(default=None, max_length=255)
    created_on: Optional[datetime] = Field(default=None)
    request_type: Optional[str] = Field(default=None, max_length=255)
    active_approval: Optional[bool] = Field(default=None)
    deactive_approval: Optional[bool] = Field(default=None)
    updated_by: Optional[str] = Field(default=None, max_length=255)
    updated_at: Optional[datetime] = Field(default=None)


class InterviewRound(SQLModel, table=True):
    __tablename__ = "tb_interview_round"
 
    id: Optional[int] = Field(default=None, primary_key=True)
    round_order: Optional[int] = Field(default=None)
    stage_name: Optional[str] = Field(default=None, max_length=255)
    stage_type: Optional[str] = Field(default=None, max_length=255)
    interview_mode: Optional[str] = Field(default=None, max_length=255)
    mandatory: Optional[bool] = Field(default=None)
    stage_type_id: Optional[int] = Field(default=None)
    interview_plan_id: Optional[int] = Field(default=None)

 
 
class InterviewCurrentStage(SQLModel, table=True):
    __tablename__ = "tb_interview_current_stage"
 
    id: Optional[int] = Field(default=None, primary_key=True)
    interviewer_id: Optional[int] = Field(default=None)
    application_id: Optional[int] = Field(default=None)
    current_stage_type: Optional[int] = Field(default=None)
    to_schedule: Optional[bool] = Field(default=None)
    interview_completed: Optional[bool] = Field(default=None)
    interview_completed_on: Optional[datetime] = Field(default=None)
    interview_date: Optional[datetime] = Field(default=None)
    feedback: Optional[bool] = Field(default=None)
    round_order: Optional[int] = Field(default=None)


class InterviewAssignment(SQLModel, table=True):
    __tablename__ = "tb_interview_assignment"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: Optional[int] = Field(default=None)
    plan_id: Optional[int] = Field(default=None)
    round_id: Optional[int] = Field(default=None)
    stage_type_id: Optional[int] = Field(default=None)
    stage_name: Optional[str] = Field(default=None, max_length=255)
    interviewer_user_id: Optional[int] = Field(default=None)
    interviewer_name: Optional[str] = Field(default=None, max_length=255)
    role_name: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = Field(default=None, max_length=255)
    comments: Optional[str] = Field(default=None, sa_column=Column(Text))
    responded_at: Optional[datetime] = Field(default=None)
    created_by: Optional[str] = Field(default=None, max_length=255)
    created_at: Optional[datetime] = Field(default=None)
    job_title: Optional[str] = Field(default=None, max_length=255)
    dept_name: Optional[str] = Field(default=None, max_length=255)
    plan_name: Optional[str] = Field(default=None, max_length=255)
    user_id: Optional[int] = Field(default=None)
    priority: Optional[int] = Field(default=None)

class InterviewFeedback(SQLModel, table=True):
    __tablename__ = "tb_interview_feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    applicant_id: Optional[int] = Field(default=None)
    interview_type: Optional[str] = Field(default=None, max_length=255)
    current_stage_id: Optional[int] = Field(default=None)
    overall_rating: Optional[int] = Field(default=None)
    technical_knowledge: Optional[int] = Field(default=None)
    communication: Optional[int] = Field(default=None)
    problem_solving: Optional[int] = Field(default=None)
    analytical_thinking: Optional[int] = Field(default=None)
    cultural_fit: Optional[int] = Field(default=None)
    strengths: Optional[str] = Field(default=None, sa_column=Column(Text))
    areas_of_improvements: Optional[str] = Field(default=None, sa_column=Column(Text))
    additional_comments: Optional[str] = Field(default=None, sa_column=Column(Text))
    decision: Optional[str] = Field(default=None, max_length=255)
    submitted_on: Optional[datetime] = Field(default=None)
    submitted_by: Optional[str] = Field(default=None, max_length=255)
    user_id: Optional[int] = Field(default=None)
    interview_mode: Optional[str] = Field(default=None, max_length=255)