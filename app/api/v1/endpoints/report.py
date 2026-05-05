import logging
import traceback
import math
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from datetime import datetime
from app.db.session import get_session
from app.models import (
    Jobs,
    JobDetails,
    JobApplications,
    ResumeAnalysis,
    InterviewAnalysis,
    StatusEnum,
)
from app.services.reports.job_applicants_report import generate_applicants_pdf
from sqlmodel import Session, select
from app import models
from app.api import deps
from fastapi.responses import StreamingResponse
from app.services.reports.candidate_report import generate_comprehensive_report
from app.services.reports.service_requisition_report import (
    generate_service_requisition_report,
)


logger = logging.getLogger(__name__)


router = APIRouter()


def safe_int(val, default=0):
    try:
        if val is None:
            return default
        f_val = float(val)
        if math.isnan(f_val) or math.isinf(f_val):
            return default
        return int(f_val)
    except:
        return default


@router.get("/generate-candidate-report/{application_id}")
def generate_pdf_report(
    application_id: int,
    session: Session = Depends(deps.get_session),
):
    try:
        job_app = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == application_id
            )
        ).first()
        if not job_app:
            raise HTTPException(status_code=404, detail="Job Application not found")

        job_details = None
        if job_app.job_id:
            job_details = session.exec(
                select(models.JobDetails).where(
                    models.JobDetails.job_id == job_app.job_id
                )
            ).first()

        job_meta = None
        if job_app.job_id:
            job_meta = session.exec(
                select(models.Jobs).where(models.Jobs.job_id == job_app.job_id)
            ).first()

        resume_analysis = session.exec(
            select(models.ResumeAnalysis).where(
                models.ResumeAnalysis.application_id == application_id
            )
        ).first()

        interview_session = session.exec(
            select(models.InterviewSessions).where(
                models.InterviewSessions.application_id == application_id
            )
        ).first()

        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                models.InterviewAnalysis.application_id == application_id
            )
        ).first()

        qna_list = []
        if interview_analysis:
            qna_results = session.exec(
                select(models.QNA_Analysis).where(
                    models.QNA_Analysis.interview_analysis_id == interview_analysis.id
                )
            ).all()
            qna_list = list(qna_results)

        proctoring_logs = []
        if interview_analysis:
            proc_results = session.exec(
                select(models.ProctoringLogs).where(
                    models.ProctoringLogs.interview_analysis_id == interview_analysis.id
                )
            ).all()
            proctoring_logs = list(proc_results)

        report_data = {
            "job_application": job_app,
            "job_details": job_details,
            "job_meta": job_meta,
            "resume_analysis": resume_analysis,
            "interview_session": interview_session,
            "interview_analysis": interview_analysis,
            "qna_list": qna_list,
            "proctoring_logs": proctoring_logs,
        }

        pdf_buffer = generate_comprehensive_report(report_data)

        candidate_name = (
            f"{job_app.first_name or ''} {job_app.last_name or ''}".strip()
            or "Candidate"
        )
        job_title = job_meta.job_title if job_meta and job_meta.job_title else "Job"

        clean_candidate = (
            "".join(c for c in candidate_name if c.isalnum() or c == " ")
            .strip()
            .replace(" ", "_")
        )
        clean_job = (
            "".join(c for c in job_title if c.isalnum() or c == " ")
            .strip()
            .replace(" ", "_")
        )

        filename = f"{clean_candidate}_{clean_job}_Report.pdf"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF report: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to generate PDF report")


@router.get("/generate-applicants-report/{job_id}")
async def generate_applicants_report(
    job_id: int, session: Session = Depends(get_session)
):
    try:
        # Try finding in JobDetails first (as applications usually link to its ID)
        job_details = session.exec(
            select(JobDetails).where(JobDetails.job_id == job_id)
        ).first()
        job = session.exec(select(Jobs).where(Jobs.job_id == job_id)).first()

        logger.warning(f"DEBUG - Job ID: {job_id}")
        logger.warning(f"DEBUG - JobDetails: {job_details}")
        logger.warning(f"DEBUG - JobMaster: {job}")

        if not job_details:
            # Fallback to Jobs table
            job_master = session.exec(select(Jobs).where(Jobs.job_id == job_id)).first()
            if not job_master:
                raise HTTPException(status_code=404, detail="Job/Details not found")
            job_title = job_master.job_title
            location = job_master.job_location
            employment_type = job_master.job_type
            # If we only have job_master, applications might still be linked to a JobDetails entry
            # that has job_master.job_id
            job_details = session.exec(
                select(JobDetails).where(JobDetails.job_id == job_id)
            ).first()
        else:
            job_title = job.job_title
            # Try to get more info from master Jobs table
            job_master = session.exec(
                select(Jobs).where(Jobs.job_id == job_details.job_id)
            ).first()
            location = job_master.job_location if job_master else "Unknown Location"
            employment_type = job_master.job_type if job_master else "Full-time"

        # Applications could be linked to either JobDetails.id or Jobs.job_id
        applications = session.exec(
            select(JobApplications).where(JobApplications.job_id == job_id)
        ).all()

        # If none found, try the JobDetails.job_id (which maps to master Jobs)
        if not applications and job_details and job_details.job_id:
            applications = session.exec(
                select(JobApplications).where(
                    JobApplications.job_id == job_details.job_id
                )
            ).all()

        # NEW: Fetch ALL ResumeAnalysis for these applicants across ANY job to ensure maximum data recovery
        app_emails = [app.email for app in applications if app.email]
        target_job_id = job_details.job_id if job_details else job_id

        # Primary: Analysis for this specific job
        job_analysis = session.exec(
            select(ResumeAnalysis).where(ResumeAnalysis.job_id == target_job_id)
        ).all()
        # Secondary: Any analysis for these candidates (if they applied elsewhere)
        other_analysis = (
            session.exec(
                select(ResumeAnalysis).where(ResumeAnalysis.email.in_(app_emails))
            ).all()
            if app_emails
            else []
        )

        # NEW: Fetch all interview analysis for this job
        app_ids = [app.id for app in applications]
        job_interview_analysis = (
            session.exec(
                select(InterviewAnalysis).where(
                    InterviewAnalysis.application_id.in_(app_ids)
                )
            ).all()
            if app_ids
            else []
        )

        # Merge them, prioritizing the one for this job
        analysis_map = {ra.email.lower(): ra for ra in other_analysis if ra.email}
        for ra in job_analysis:
            if ra.email:
                analysis_map[ra.email.lower()] = ra
        # Also map by ID and fetch all interviews for mapping
        id_map = {ra.application_id: ra for ra in job_analysis if ra.application_id}
        job_interviews = session.exec(
            select(InterviewAnalysis).where(InterviewAnalysis.job_id == target_job_id)
        ).all()
        interview_map = {
            ia.application_id: ia for ia in job_interviews if ia.application_id
        }

        logger.info(
            f"Report Data: Found {len(job_analysis)} screening records and {len(job_interview_analysis)} interview records for job {target_job_id}"
        )

        # Log Experience Distribution from DB
        exp_counts = {"Experience": 0, "Intermediate": 0, "Beginer": 0}
        for ra in job_analysis:
            raw_e = str(ra.experience_level or "").strip().lower()
            if raw_e in ["experienced", "experience"]:
                exp_counts["Experience"] += 1
            elif raw_e == "intermediate":
                exp_counts["Intermediate"] += 1
            else:
                exp_counts["Beginer"] += 1
        logger.warning(f"DEBUG - Experience Distribution from DB: {exp_counts}")

        applicants_data = []
        for app in applications:
            # Multi-layered lookup for Resume Analysis
            resume_analysis = id_map.get(app.id)
            if not resume_analysis and app.email:
                resume_analysis = analysis_map.get(app.email.lower())

            # Multi-layered lookup for Interview Analysis
            interview_analysis = interview_map.get(app.id)
            if not interview_analysis and resume_analysis:
                interview_analysis = interview_map.get(resume_analysis.application_id)

            candidate_name = (
                f"{app.first_name or ''} {app.last_name or ''}".strip()
                or "Unknown Candidate"
            )
            applied_on = (
                app.created_date.strftime("%d %b %Y") if app.created_date else ""
            )

            # Use standardized mapping from tb_resume_analysis table to handle DB inconsistencies
            if resume_analysis:
                raw_exp = str(resume_analysis.experience_level or "").strip().lower()
                if raw_exp in ["experienced", "experience"]:
                    experience = "Experience"
                elif raw_exp in ["intermediate"]:
                    experience = "Intermediate"
                else:
                    experience = "Beginer"
                screening_score = f"{safe_int(resume_analysis.final_score)}%"
                shortlisted = (
                    "Yes"
                    if resume_analysis.status
                    in ["Shortlisted", "Offered", "In Process"]
                    else "No"
                )
                status = resume_analysis.status or "Applied"
            else:
                experience = "Beginer"
                screening_score = "-"
                shortlisted = "No"
                status = "Applied"

            if interview_analysis:
                ai_interview = (
                    "Yes" if interview_analysis.status == StatusEnum.completed else "No"
                )
                interview_score = (
                    f"{safe_int(interview_analysis.total_score, default='-')}%"
                    if interview_analysis.total_score is not None
                    else "-"
                )
                if interview_analysis.final_decision:
                    status = interview_analysis.final_decision
            else:
                ai_interview = "No"
                interview_score = "-"

            # Track which analysis record we used to avoid missing any in the chart
            used_analysis_id = resume_analysis.id if resume_analysis else None

            applicant_info = {
                "name": candidate_name,
                "experience": experience,
                "company": "-",
                "applied_on": applied_on,
                "screening_score": screening_score,
                "shortlisted": shortlisted,
                "screened": "Yes" if resume_analysis else "No",
                "ai_interview": ai_interview,
                "interview_score": interview_score,
                "interview_score_raw": (
                    interview_analysis.total_score if interview_analysis else None
                ),
                "status": status.title(),
                "score": screening_score,
                "screening_score_raw": (
                    resume_analysis.final_score if resume_analysis else None
                ),
                "analysis_id": used_analysis_id,
                "source": app.source,
            }
            applicants_data.append(applicant_info)

        # 4. Add "Ghost" entries for any ResumeAnalysis records that were NOT matched to an application
        # This ensures the charts are 100% accurate to the tb_resume_analysis table
        matched_analysis_ids = {
            a["analysis_id"] for a in applicants_data if a.get("analysis_id")
        }
        for ra in job_analysis:
            if ra.id not in matched_analysis_ids:
                # Same standardized mapping for ghost entries
                raw_exp = str(ra.experience_level or "").strip().lower()
                if raw_exp in ["experienced", "experience"]:
                    exp_to_use = "Experience"
                elif raw_exp in ["intermediate"]:
                    exp_to_use = "Intermediate"
                else:
                    exp_to_use = "Beginer"

                applicants_data.append(
                    {
                        "name": ra.candidate_name or "Unknown",
                        "experience": exp_to_use,
                        "screening_score": f"{safe_int(ra.final_score)}%",
                        "screening_score_raw": ra.final_score,
                        "interview_score_raw": None,  # Ghosts have no interview yet
                        "status": (ra.status or "Applied").title(),
                        "is_ghost": True,  # Flag to hide from details table but include in charts
                        "source": "Others",
                    }
                )

        requisition_id = (
            job_master.job_code if job_master and job_master.job_code else "N/A"
        )
        date_posted = (
            job_master.created_date.strftime("%d %b %Y")
            if job_master and job_master.created_date
            else "N/A"
        )

        # Calculate summary counts directly from database record lists for 100% accuracy
        screened_count = len(job_analysis)
        shortlisted_count = sum(
            1 for ra in job_analysis if ra.status in ["Shortlisted", "Offered"]
        )
        offered_count = sum(1 for ra in job_analysis if ra.status == "Offered")
        ai_interview_count = len(job_interview_analysis)  # All interviews for this job

        pdf_buffer = generate_applicants_pdf(
            job_title=job_title or "Unknown Title",
            department="Engineering",
            location=location or "Unknown Location",
            employment_type=employment_type or "Full-time",
            applicants=applicants_data,
            report_date=datetime.now().strftime("%d %b %Y | %I:%M %p"),
            requisition_id=requisition_id,
            date_posted=date_posted,
            # Pass raw database records for 100% accurate charts
            raw_analysis_records=job_analysis,
            raw_interview_records=job_interview_analysis,
        )

        clean_job_title = (job_title or "Job").replace(" ", "_")
        filename = f"{clean_job_title}_ApplicantsReport.pdf"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF report: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF report: {str(e)}",
        )


@router.get("/generate-service-requisition-report/{id}")
async def generate_service_requisition_report_endpoint(
    id: int, session: Session = Depends(get_session)
):
    try:
        sr_position = session.exec(
            select(models.SrPositionBasics).where(models.SrPositionBasics.id == id)
        ).first()
        if not sr_position:
            raise HTTPException(status_code=404, detail="Service Requisition not found")

        reporting_manger_info = session.exec(
            select(models.ChildReportingManagerInfo).where(
                models.ChildReportingManagerInfo.staffing_requisition_id == id
            )
        ).first()

        sr_id = sr_position.sr_id

        sr_business = (
            session.exec(
                select(models.SrBusinessJustification).where(
                    models.SrBusinessJustification.sr_id == sr_id
                )
            ).first()
            if sr_id
            else None
        )

        budget_comp = (
            session.exec(
                select(models.BudgetCompensation).where(
                    models.BudgetCompensation.sr_id == sr_id
                )
            ).first()
            if sr_id
            else None
        )

        roles_req = (
            session.exec(
                select(models.RolesRequirements).where(
                    models.RolesRequirements.sr_id == sr_id
                )
            ).first()
            if sr_id
            else None
        )

        sourcing_entity = (
            session.exec(
                select(models.SourcingEntity).where(
                    models.SourcingEntity.sr_id == sr_id
                )
            ).first()
            if sr_id
            else None
        )

        business_unit = None
        if sr_position.business_unit:
            business_unit = session.exec(
                select(models.BusinessUnit).where(
                    models.BusinessUnit.id == sr_position.business_unit
                )
            ).first()

        department = None
        if sr_position.department:
            department = session.exec(
                select(models.Departments).where(
                    models.Departments.id == sr_position.department
                )
            ).first()

        seniority_level = None
        if sr_position.seniority_level:
            seniority_level = session.exec(
                select(models.SeniorityLevel).where(
                    models.SeniorityLevel.id == sr_position.seniority_level
                )
            ).first()

        creator = None
        if sr_position.created_by:
            try:
                creator_id = int(sr_position.created_by)
                creator = session.exec(
                    select(models.User).where(
                        (models.User.id == creator_id)
                        | (models.User.user_id == creator_id)
                        | (models.User.employee_id == creator_id)
                    )
                ).first()
            except ValueError:
                creator = session.exec(
                    select(models.User).where(
                        models.User.email == sr_position.created_by
                    )
                ).first()

        section_0 = dict()
        section_1 = dict()  # springboot dependency
        section_2 = dict()
        section_3 = dict()
        section_4 = dict()
        section_5 = dict()
        section_6 = dict()  # todo
        section_7 = dict()  # todo

        section_0["sr_id"] = sr_position.sr_id if sr_position.sr_id else "N/A"
        section_0["approved"] = sr_position.approved if sr_position.approved else False
        section_0["creator_name"] = (
            f"{creator.first_name} {creator.last_name}".strip()
            if creator
            else (sr_position.created_by or "N/A")
        )
        section_0["department_name"] = (
            department.department_name if department else "N/A"
        )
        section_0["created_on"] = (
            sr_position.created_on if sr_position.created_on else "N/A"
        )
        section_0["priority"] = sr_position.priority if sr_position.priority else "N/A"
        section_0["target_start_date"] = (
            sr_position.target_start_date if sr_position.target_start_date else "N/A"
        )

        if roles_req and roles_req.min_experience and roles_req.max_experience:
            experience = (
                str(roles_req.min_experience)
                + " - "
                + str(roles_req.max_experience)
                + " Years"
            )
        else:
            experience = "N/A"

        reporting_manager_model = session.exec(
            select(models.User).where(
                models.User.id == reporting_manger_info.reporting_manager_ids
            )
        ).first()

        if reporting_manager_model and (
            reporting_manager_model.first_name or reporting_manager_model.last_name
        ):
            reporting_manager = (
                reporting_manager_model.first_name
                + " "
                + reporting_manager_model.last_name
            )
        else:
            reporting_manager = "N/A"

        section_2["job_title"] = (
            sr_position.job_title if sr_position and sr_position.job_title else "N/A"
        )
        section_2["business_unit"] = (
            sr_position.business_unit
            if sr_position and sr_position.business_unit
            else "N/A"
        )
        section_2["department"] = (
            department.department_name
            if department and department.department_name
            else "N/A"
        )
        section_2["reporting_manager"] = reporting_manager
        section_2["employment_type"] = (
            sr_position.employment_type
            if sr_position and sr_position.employment_type
            else "N/A"
        )
        section_2["work_mode"] = (
            sr_position.work_mode if sr_position and sr_position.work_mode else "N/A"
        )
        section_2["location"] = (
            sr_position.location if sr_position and sr_position.location else "N/A"
        )
        section_2["target_start_date"] = (
            sr_position.target_start_date
            if sr_position and sr_position.target_start_date
            else "N/A"
        )
        section_2["openings"] = (
            sr_position.openings if sr_position and sr_position.openings else "N/A"
        )
        section_2["experience"] = experience
        section_2["seniority_level"] = (
            sr_position.seniority_level
            if sr_position and sr_position.seniority_level
            else "N/A"
        )
        section_2["priority"] = (
            sr_position.priority if sr_position and sr_position.priority else "N/A"
        )

        section_3["requisition_type"] = (
            sr_business.requisition_type
            if sr_business and sr_business.requisition_type
            else "N/A"
        )
        section_3["replaces_employee"] = (
            sr_business.replaces_employee
            if sr_business and sr_business.replaces_employee
            else "N/A"
        )
        section_3["impact_if_not_filled"] = (
            sr_business.impact_if_not_filled
            if sr_business and sr_business.impact_if_not_filled
            else "N/A"
        )
        section_3["business_case"] = (
            sr_business.business_case
            if sr_business and sr_business.business_case
            else "N/A"
        )

        if budget_comp and budget_comp.minimum_salary and budget_comp.maximum_salary:
            salary_band = (
                str(budget_comp.minimum_salary)
                + " - "
                + str(budget_comp.maximum_salary)
                + "LPA"
            )
        else:
            salary_band = "N/A"

        if budget_comp and budget_comp.signing_bonus:
            signing_bonus = budget_comp.signing_bonus_amount
        else:
            signing_bonus = "N/A"

        if budget_comp and budget_comp.equity:
            equity = budget_comp.equity_amount
        else:
            equity = "N/A"

        if budget_comp and budget_comp.relocation_budget:
            relocation_budget = budget_comp.relocation_budget
        else:
            relocation_budget = "N/A"

        section_4["minimum_salary"] = (
            budget_comp.minimum_salary
            if budget_comp and budget_comp.minimum_salary
            else "N/A"
        )
        section_4["maximum_salary"] = (
            budget_comp.maximum_salary
            if budget_comp and budget_comp.maximum_salary
            else "N/A"
        )
        section_4["proposed_total_compensation"] = (
            budget_comp.proposed_total_compensation
            if budget_comp and budget_comp.proposed_total_compensation
            else "N/A"
        )
        section_4["annual_hiring_cost"] = (
            budget_comp.annual_hiring_cost
            if budget_comp and budget_comp.annual_hiring_cost
            else "N/A"
        )
        section_4["signing_bonus"] = signing_bonus
        section_4["equity"] = equity
        section_4["relocation_budget"] = relocation_budget

        if roles_req and roles_req.min_experience and roles_req.max_experience:
            years_of_experience = (
                str(roles_req.min_experience)
                + " - "
                + str(roles_req.max_experience)
                + " Years"
            )
        else:
            years_of_experience = "N/A"

        if roles_req and roles_req.min_interviews and roles_req.max_interviews:
            interview_rounds = (
                str(roles_req.min_interviews)
                + " - "
                + str(roles_req.max_interviews)
                + " Rounds"
            )
        else:
            interview_rounds = "N/A"

        section_5["skills_must_have"] = (
            roles_req.skills_must_have.replace(",", ", ")
            if roles_req and roles_req.skills_must_have
            else "N/A"
        )
        section_5["nice_to_have_skills"] = (
            roles_req.nice_to_have_skills.replace(",", ", ")
            if roles_req and roles_req.nice_to_have_skills
            else "N/A"
        )
        section_5["education_requirements"] = (
            roles_req.education_requirements
            if roles_req and roles_req.education_requirements
            else "N/A"
        )
        section_5["years_of_experience"] = years_of_experience
        section_5["interview_rounds"] = interview_rounds
        section_5["certifications_required"] = (
            roles_req.certifications_required.replace(",", ", ")
            if roles_req and roles_req.certifications_required
            else "N/A"
        )
        section_5["languages"] = (
            roles_req.languages if roles_req and roles_req.languages else "N/A"
        )
        section_5["assessment_required"] = (
            "Yes" if roles_req and roles_req.assessment_required else "No"
        )
        section_5["travel_requirements"] = (
            roles_req.travel_requirements
            if roles_req and roles_req.travel_requirements
            else "N/A"
        )

        report_data = {
            "section_0": section_0,
            "section_2": section_2,
            "section_3": section_3,
            "section_4": section_4,
            "section_5": section_5,
            "generated_on": datetime.now().isoformat(),
        }

        pdf_buffer = generate_service_requisition_report(report_data)

        sr_id_format = (sr_position.sr_id or "SR").replace("-", "_")
        filename = f"{sr_id_format}_Service_Requisition_Report.pdf"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating service requisition report: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate service requisition report: {str(e)}",
        )
