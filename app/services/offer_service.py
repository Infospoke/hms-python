from datetime import datetime
from sqlmodel import Session, select
from app.models import JobApplications, CreateJobDetails, User, BudgetCompensation, OfferDetails

def generate_reference_id(application_id: int) -> str:
    return f"INF/{datetime.now().year}/{application_id:06d}"

def get_offer_details(db: Session, request, force_budget_ctc: bool = False):
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

    # Reporting Manager
    manager_name = None
    if job and job.created_by:
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
    if job and job.sr_id:
        # Try 1: Exact sr_id match
        budget = db.exec(
            select(BudgetCompensation).where(BudgetCompensation.sr_id == job.sr_id)
        ).first()

        # Try 2: Numeric fallback (e.g. 'SR001' -> ID 1)
        if not budget:
            try:
                digits = "".join([c for c in job.sr_id if c.isdigit()])
                if digits:
                    sr_num_id = int(digits)
                    budget = db.exec(
                        select(BudgetCompensation).where(BudgetCompensation.id == sr_num_id)
                    ).first()
            except Exception:
                pass

        # Try 3: Substring match
        if not budget:
            try:
                all_budgets = db.exec(select(BudgetCompensation)).all()
                for b in all_budgets:
                    if b.sr_id and (b.sr_id in job.sr_id or job.sr_id in b.sr_id):
                        budget = b
                        break
            except Exception:
                pass

    # Try 4: Table fallback
    if not budget:
        try:
            budget = db.exec(select(BudgetCompensation)).first()
        except Exception:
            pass

    joining_date_str = None
    if job and job.target_start_date:
        # Assuming target_start_date is a date or datetime object
        try:
            joining_date_str = job.target_start_date.strftime("%d-%m-%Y")
        except AttributeError:
            joining_date_str = str(job.target_start_date)

    # Check if there is an existing OfferDetails record with updated total_ctc
    offer_detail = None
    if not force_budget_ctc:
        offer_detail = db.exec(
            select(OfferDetails).where(
                (OfferDetails.job_application_id == request.application_id) |
                (OfferDetails.id == request.application_id)
            )
        ).first()

    if offer_detail and offer_detail.total_ctc is not None:
        ctc_val = float(offer_detail.total_ctc)
    else:
        ctc_val = float(budget.annual_hiring_cost) if (budget and budget.annual_hiring_cost) else 0.0

    basic_salary = ctc_val * 0.5
    other_benefits = ctc_val - basic_salary

    return {
        "reference_id": generate_reference_id(request.application_id),
        "date": datetime.now().strftime("%d-%m-%Y"),
        "candidate_name": f"{candidate.first_name or ''} {candidate.last_name or ''}".strip(),
        "joining_date": joining_date_str,
        "job_title": job.job_title if job else "Employee",
        "reporting_manager": manager_name,
        "ctc": ctc_val,
        "basic_salary": basic_salary,
        "signing_bonus": request.signing_bonus,
        "equity_rsu": request.equity_rsu,
        "other_benefits": other_benefits,
        "notice_period": request.notice_period
    }
