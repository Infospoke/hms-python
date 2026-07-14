from datetime import datetime
from sqlmodel import Session, select
from app.models import JobApplications, CreateJobDetails, User, BudgetCompensation

def generate_reference_id(application_id: int) -> str:
    return f"INF/{datetime.now().year}/{application_id:06d}"

def get_offer_details(db: Session, request):
    # Candidate Name
    candidate = db.exec(
        select(JobApplications).where(JobApplications.id == request.application_id)
    ).first()
    
    if not candidate:
        raise Exception("Application not found")

    # Job Details
    job = db.exec(
        select(CreateJobDetails).where(CreateJobDetails.job_id == request.job_id)
    ).first()

    if not job:
        raise Exception("Job not found")

    # Reporting Manager
    manager_name = None
    if job.created_by:
        manager = db.exec(
            select(User.first_name, User.last_name).where(User.email == job.created_by)
        ).first()
        if not manager:
            try:
                creator_id = int(job.created_by)
                manager = db.exec(
                    select(User.first_name, User.last_name).where(
                        (User.id == creator_id) | 
                        (User.user_id == creator_id) | 
                        (User.employee_id == creator_id)
                    )
                ).first()
            except ValueError:
                pass
        
        if manager:
            manager_name = f"{manager.first_name} {manager.last_name}".strip()

    # Budget Compensation
    budget = None
    if job.sr_id:
        budget = db.exec(
            select(BudgetCompensation).where(BudgetCompensation.sr_id == job.sr_id)
        ).first()

    joining_date_str = None
    if job.target_start_date:
        # Assuming target_start_date is a date or datetime object
        try:
            joining_date_str = job.target_start_date.strftime("%d-%m-%Y")
        except AttributeError:
            joining_date_str = str(job.target_start_date)

    return {
        "reference_id": generate_reference_id(request.application_id),
        "date": datetime.now().strftime("%d-%m-%Y"),
        "candidate_name": f"{candidate.first_name or ''} {candidate.last_name or ''}".strip(),
        "joining_date": joining_date_str,
        "job_title": job.job_title,
        "reporting_manager": manager_name,
        "ctc": budget.annual_hiring_cost if (budget and budget.annual_hiring_cost) else 0,
        "basic_salary": request.basic_salary,
        "signing_bonus": request.signing_bonus,
        "equity_rsu": request.equity_rsu,
        "other_benefits": request.other_benefits,
        "notice_period": request.notice_period
    }
