import logging
import traceback
import math
from fastapi import APIRouter, HTTPException, status, Response, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from datetime import datetime
from app.db.session import get_session
from app.models import Jobs, JobDetails, JobApplications, ResumeAnalysis, InterviewAnalysis, StatusEnum
from app.core import config as consts
from app.services.pdf_generator import generate_applicants_pdf
from app.schemas import (
    AISuggestSkillsRequest,
    AISuggestSkillsResponse,
    SkillRequirement,
    GenerateJobDescriptionRequest,
    GenerateApplicantsReportRequest,
)
from app.utils.recomended_roles import SkillGenerator, JobDescriptionGenerator
from app.utils.ctc_validation_helper import fetch_salary_benchmarks
from app.schemas import (
    CTCReviewRequest,
    CTCReviewResponse,
    JobRequirementsRequest,
    CertificationsResponse,
    LanguagesResponse,
    QualificationsResponse,
)
from app.utils.gemini_llm import call_llm
from app.utils.requirements_helper import (
    build_certifications_prompt,
    build_languages_prompt,
    build_qualifications_prompt,
)
from sqlmodel import Session, select
from app import models
from app.api import deps
from fastapi.responses import StreamingResponse
from app.services.pdf_generator import generate_comprehensive_report


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


@router.post("/config/refresh")
def refresh_interview_configs():
    try:
        consts._load_interview_configs()

        loaded_keys = (
            list(consts._INTERVIEW_CONFIGS_CACHE.keys())
            if consts._INTERVIEW_CONFIGS_CACHE
            else []
        )
        logger.info(f"Config refresh successful. Loaded keys: {loaded_keys}")

        return {
            "status": "ok",
            "message": "Interview configurations refreshed successfully from database.",
            "loaded_keys": loaded_keys,
            "total_count": len(loaded_keys),
        }
    except Exception as e:
        logger.error(f"Config refresh failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh interview configurations: {str(e)}",
        )


@router.post("/ai-suggest-must-have-skills")
def ai_suggest_must_have_skills(data: AISuggestSkillsRequest):
    """Generate AI-suggested must-have (mandatory) skills based on job details."""
    try:
        generator = SkillGenerator()
        result = generator.generate_must_have_skills(
            job_title=data.job_title,
            department=data.department,
            business_case=data.business_case,
        )

        if result.get("success"):
            skills = [
                SkillRequirement(skill_title=s.get("skill_title", ""))
                for s in result.get("skills", [])
            ]
            return AISuggestSkillsResponse(
                success=True,
                skills=skills,
                message=f"AI suggested {len(skills)} must-have skills based on job details",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate must-have skills: {result.get('error')}",
            )

    except Exception as e:
        logger.error(f"Error generating AI must-have skills: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate AI must-have skills",
        )


@router.post("/ai-suggest-nice-to-have-skills")
def ai_suggest_nice_to_have_skills(data: AISuggestSkillsRequest):
    """Generate AI-suggested nice-to-have (optional) skills based on job details."""
    try:
        generator = SkillGenerator()
        result = generator.generate_nice_to_have_skills(
            job_title=data.job_title,
            department=data.department,
            business_case=data.business_case,
        )

        if result.get("success"):
            skills = [
                SkillRequirement(skill_title=s.get("skill_title", ""))
                for s in result.get("skills", [])
            ]
            return AISuggestSkillsResponse(
                success=True,
                skills=skills,
                message=f"AI suggested {len(skills)} nice-to-have skills based on job details",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate nice-to-have skills: {result.get('error')}",
            )

    except Exception as e:
        logger.error(f"Error generating AI nice-to-have skills: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate AI nice-to-have skills",
        )


@router.post("/generate-job-description")
def generate_job_description(data: GenerateJobDescriptionRequest):
    """Generate a comprehensive job description using AI based on job details."""
    try:
        generator = JobDescriptionGenerator()
        result = generator.generate_job_description(
            job_title=data.job_title,
            department=data.department,
            location=data.location,
            seniority_level=data.seniority_level,
            num_openings=data.num_openings,
            target_start_date=data.target_start_date,
            employment_type=data.employment_type,
            work_mode=data.work_mode,
            must_have_skills=data.must_have_skills,
            nice_to_have_skills=data.nice_to_have_skills,
            education_requirements=data.education_requirements,
            travel_requirement=data.travel_requirement,
            years_of_experience=data.years_of_experience,
            required_certifications=data.required_certifications,
            languages=data.languages,
        )

        if result.get("success"):
            jd_data = result.get("job_description", {})

            # Generate formatted text string
            job_summary = jd_data.get("job_summary", "")
            key_responsibilities = jd_data.get("key_responsibilities", [])
            required_qualifications = jd_data.get("required_qualifications", [])
            preferred_qualifications = jd_data.get("preferred_qualifications", [])
            skills_must_have = jd_data.get("skills_must_have", [])
            skills_nice_to_have = jd_data.get("skills_nice_to_have", [])
            education_requirements = jd_data.get("education_requirements", "")
            experience_requirements = jd_data.get("experience_requirements", "")
            languages_required = jd_data.get("languages_required", "")
            travel_requirement = jd_data.get("travel_requirement", "")
            work_mode = jd_data.get("work_mode", "")
            employment_type = jd_data.get("employment_type", "")
            location = jd_data.get("location", "")
            about_company = jd_data.get("about_company", "")

            # Build text string
            text_parts = [job_summary, ""]
            text_parts.append("Key Responsibilities:")
            text_parts.extend([f"- {resp}" for resp in key_responsibilities])
            text_parts.append("")
            text_parts.append("Required Qualifications:")
            text_parts.extend([f"- {qual}" for qual in required_qualifications])
            text_parts.append("")
            if preferred_qualifications:
                text_parts.append("Preferred Qualifications:")
                text_parts.extend([f"- {qual}" for qual in preferred_qualifications])
                text_parts.append("")
            text_parts.append(f"Must-Have Skills: {', '.join(skills_must_have)}")
            text_parts.append(f"Nice-to-Have Skills: {', '.join(skills_nice_to_have)}")
            text_parts.append(f"Education Requirements: {education_requirements}")
            text_parts.append(f"Experience Requirements: {experience_requirements}")
            text_parts.append(f"Languages Required: {languages_required}")
            text_parts.append(f"Travel Requirement: {travel_requirement}")
            text_parts.append(f"Work Mode: {work_mode}")
            text_parts.append(f"Employment Type: {employment_type}")
            text_parts.append(f"Location: {location}")
            text_parts.append(f"About Company: {about_company}")

            job_description_text = "\n".join(text_parts)

            return Response(content=job_description_text, media_type="text/plain")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate job description: {result.get('error')}",
            )

    except Exception as e:
        logger.error(f"Error generating job description: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate job description",
        )


@router.post("/ctc-review", response_model=CTCReviewResponse)
async def ctc_review(req: CTCReviewRequest):
    benchmarks = await fetch_salary_benchmarks(
        job_title=req.job_title,
        location=req.location,
        employment_type=req.employment_type,
        seniority=req.seniority,
    )

    # if not benchmarks:
    #     return CTCReviewResponse(min_salary=0, max_salary=0)

    # return CTCReviewResponse(
    #     min_salary=benchmarks[0].min_salary if benchmarks[0].min_salary else 0,
    #     max_salary=benchmarks[0].max_salary if benchmarks[0].max_salary else 0,
    # )

    return CTCReviewResponse(
        min_salary=300000,
        max_salary=500000
    )


@router.post("/certifications-suggestions", response_model=CertificationsResponse)
async def get_certifications_suggestions(req: JobRequirementsRequest):
    prompt = build_certifications_prompt(req)

    try:
        llm_resp = await call_llm(prompt)
        return CertificationsResponse(certifications=llm_resp.get("certifications", []))
    except Exception as e:
        logger.error(f"Certifications suggestions failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate certification suggestions: {str(e)}",
        )


@router.post("/language-suggestions", response_model=LanguagesResponse)
async def get_language_suggestions(req: JobRequirementsRequest):
    prompt = build_languages_prompt(req)

    try:
        llm_resp = await call_llm(prompt)
        return LanguagesResponse(languages=llm_resp.get("languages", []))
    except Exception as e:
        logger.error(f"Language suggestions failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate language suggestions: {str(e)}",
        )


@router.post("/qualifications-suggestions", response_model=QualificationsResponse)
async def get_qualifications_suggestions(req: JobRequirementsRequest):
    prompt = build_qualifications_prompt(req)

    try:
        llm_resp = await call_llm(prompt)
        return QualificationsResponse(qualifications=llm_resp.get("qualifications", []))
    except Exception as e:
        logger.error(f"Qualifications suggestions failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate qualification suggestions: {str(e)}",
        )


@router.get("/report/{application_id}")
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

        candidate_name = f"{job_app.first_name or ''} {job_app.last_name or ''}".strip() or "Candidate"
        job_title = job_meta.job_title if job_meta and job_meta.job_title else "Job"

        clean_candidate = "".join(c for c in candidate_name if c.isalnum() or c == " ").strip().replace(" ", "_")
        clean_job = "".join(c for c in job_title if c.isalnum() or c == " ").strip().replace(" ", "_")

        filename = f"{clean_candidate}_{clean_job}_Report.pdf"

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF report: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to generate PDF report")


@router.get("/generate-applicants-report/{job_id}")
async def generate_applicants_report(job_id: int, session: Session = Depends(get_session)):
    try:
        # Try finding in JobDetails first (as applications usually link to its ID)
        job_details = session.exec(select(JobDetails).where(JobDetails.job_id == job_id)).first()
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
            job_details = session.exec(select(JobDetails).where(JobDetails.job_id == job_id)).first()
        else:
            job_title = job.job_title
            # Try to get more info from master Jobs table
            job_master = session.exec(select(Jobs).where(Jobs.job_id == job_details.job_id)).first()
            location = job_master.job_location if job_master else "Unknown Location"
            employment_type = job_master.job_type if job_master else "Full-time"

        # Applications could be linked to either JobDetails.id or Jobs.job_id
        applications = session.exec(select(JobApplications).where(JobApplications.job_id == job_id)).all()
        
        # If none found, try the JobDetails.job_id (which maps to master Jobs)
        if not applications and job_details and job_details.job_id:
            applications = session.exec(select(JobApplications).where(JobApplications.job_id == job_details.job_id)).all()

        # NEW: Fetch ALL ResumeAnalysis for these applicants across ANY job to ensure maximum data recovery
        app_emails = [app.email for app in applications if app.email]
        target_job_id = job_details.job_id if job_details else job_id
        
        # Primary: Analysis for this specific job
        job_analysis = session.exec(select(ResumeAnalysis).where(ResumeAnalysis.job_id == target_job_id)).all()
        # Secondary: Any analysis for these candidates (if they applied elsewhere)
        other_analysis = session.exec(select(ResumeAnalysis).where(ResumeAnalysis.email.in_(app_emails))).all() if app_emails else []
        
        # NEW: Fetch all interview analysis for this job
        app_ids = [app.id for app in applications]
        job_interview_analysis = session.exec(select(InterviewAnalysis).where(InterviewAnalysis.application_id.in_(app_ids))).all() if app_ids else []
        
        # Merge them, prioritizing the one for this job
        analysis_map = {ra.email.lower(): ra for ra in other_analysis if ra.email}
        for ra in job_analysis:
            if ra.email:
                analysis_map[ra.email.lower()] = ra
        # Also map by ID and fetch all interviews for mapping
        id_map = {ra.application_id: ra for ra in job_analysis if ra.application_id}
        job_interviews = session.exec(select(InterviewAnalysis).where(InterviewAnalysis.job_id == target_job_id)).all()
        interview_map = {ia.application_id: ia for ia in job_interviews if ia.application_id}
        
        logger.info(f"Report Data: Found {len(job_analysis)} screening records and {len(job_interview_analysis)} interview records for job {target_job_id}")
        
        # Log Experience Distribution from DB
        exp_counts = {"Experience": 0, "Intermediate": 0, "Beginer": 0}
        for ra in job_analysis:
            raw_e = str(ra.experience_level or "").strip().lower()
            if raw_e in ["experienced", "experience"]: exp_counts["Experience"] += 1
            elif raw_e == "intermediate": exp_counts["Intermediate"] += 1
            else: exp_counts["Beginer"] += 1
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
            
            candidate_name = f"{app.first_name or ''} {app.last_name or ''}".strip() or "Unknown Candidate"
            applied_on = app.created_date.strftime("%d %b %Y") if app.created_date else ""

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
                shortlisted = "Yes" if resume_analysis.status in ["Shortlisted", "Offered", "In Process"] else "No"
                status = resume_analysis.status or "Applied"
            else:
                experience = "Beginer"
                screening_score = "-"
                shortlisted = "No"
                status = "Applied"

            if interview_analysis:
                ai_interview = "Yes" if interview_analysis.status == StatusEnum.completed else "No"
                interview_score = f"{safe_int(interview_analysis.total_score, default='-')}%" if interview_analysis.total_score is not None else "-"
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
                "interview_score_raw": interview_analysis.total_score if interview_analysis else None,
                "status": status.title(),
                "score": screening_score,
                "screening_score_raw": resume_analysis.final_score if resume_analysis else None,
                "analysis_id": used_analysis_id,
                "source": app.source
            }
            applicants_data.append(applicant_info)

        # 4. Add "Ghost" entries for any ResumeAnalysis records that were NOT matched to an application
        # This ensures the charts are 100% accurate to the tb_resume_analysis table
        matched_analysis_ids = {a["analysis_id"] for a in applicants_data if a.get("analysis_id")}
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
                    
                applicants_data.append({
                    "name": ra.candidate_name or "Unknown",
                    "experience": exp_to_use,
                    "screening_score": f"{safe_int(ra.final_score)}%",
                    "screening_score_raw": ra.final_score,
                    "interview_score_raw": None, # Ghosts have no interview yet
                    "status": (ra.status or "Applied").title(),
                    "is_ghost": True, # Flag to hide from details table but include in charts
                    "source": "Others"
                })

        requisition_id = job_master.job_code if job_master and job_master.job_code else "N/A"
        date_posted = job_master.created_date.strftime("%d %b %Y") if job_master and job_master.created_date else "N/A"

        # Calculate summary counts directly from database record lists for 100% accuracy
        screened_count = len(job_analysis)
        shortlisted_count = sum(1 for ra in job_analysis if ra.status in ["Shortlisted", "Offered"])
        offered_count = sum(1 for ra in job_analysis if ra.status == "Offered")
        ai_interview_count = len(job_interview_analysis) # All interviews for this job

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
            raw_interview_records=job_interview_analysis
        )

        clean_job_title = (job_title or "Job").replace(' ', '_')
        filename = f"{clean_job_title}_ApplicantsReport.pdf"

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
