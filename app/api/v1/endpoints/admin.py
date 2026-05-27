import logging
import traceback
from fastapi import APIRouter, HTTPException, status, Response
from fastapi.responses import JSONResponse
from app.core import config as consts
from app.schemas import (
    AISuggestSkillsRequest,
    AISuggestSkillsResponse,
    SkillRequirement,
    GenerateJobDescriptionRequest,
    CTCReviewRequest,
    CTCReviewResponse,
    JobRequirementsRequest,
    CertificationsResponse,
    LanguagesResponse,
    QualificationsResponse,
    CandidateRejectedRequest,
)
from app.utils.recomended_roles import SkillGenerator, JobDescriptionGenerator
from app.utils.ctc_validation_helper import fetch_salary_benchmarks

from app.utils.gemini_llm import call_llm
from app.utils.requirements_helper import (
    build_certifications_prompt,
    build_languages_prompt,
    build_qualifications_prompt,
)

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from datetime import datetime
from app.db.session import get_session
from app import models


logger = logging.getLogger(__name__)

router = APIRouter()


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
def generate_job_description(
    data: GenerateJobDescriptionRequest,
    session: Session = Depends(get_session),
):
    """Generate or rewrite a comprehensive job description using AI based on details or an old JD."""
    try:
        generator = JobDescriptionGenerator()
        if data.old_job_description and data.update_parameter:
            allowed_parameters = {
                "rewrite for senior level",
                "rewrite for junior level",
                "make concise",
                "make more technical",
                "expand responsibilities",
            }
            if data.update_parameter.lower() not in allowed_parameters:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid update_parameter.",
                )

            result = generator.rewrite_job_description(
                old_job_description=data.old_job_description,
                update_parameter=data.update_parameter,
            )
            if result.get("success"):
                rewritten_jd = result.get("job_description", {})
                return JSONResponse(content=rewritten_jd)
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to rewrite job description: {result.get('error')}",
                )

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
            return JSONResponse(content=jd_data)
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate job description: {result.get('error')}",
            )

    except HTTPException:
        raise
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

    return CTCReviewResponse(min_salary=300000, max_salary=500000)


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


@router.post("/candidate-rejected")
def candidate_rejected(
    req: CandidateRejectedRequest,
    session: Session = Depends(get_session),
):
    try:
        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == req.application_id
            )
        ).first()
        if not job_application:
            raise HTTPException(status_code=404, detail="Job Application not found")
        job_application.rejected = req.rejected
        session.add(job_application)
        session.commit()
        return {"status": "ok", "message": "Candidate rejected status updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating candidate rejected status: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail="Failed to update candidate rejected status"
        )

