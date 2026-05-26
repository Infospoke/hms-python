import logging
import traceback
from fastapi import APIRouter, HTTPException, status, Request
from app.core import config as consts
from app.schemas import (
    AISuggestSkillsRequest,
    AISuggestSkillsResponse,
    SkillRequirement,
    GenerateJobDescriptionRequest,
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
    CandidateRejectedRequest,
    JobDescriptionRevision,
    JobDescriptionRevisionsResponse,
)
from app.utils.gemini_llm import call_llm
from app.utils.requirements_helper import (
    build_certifications_prompt,
    build_languages_prompt,
    build_qualifications_prompt,
)

from fastapi import APIRouter, HTTPException, status, Depends, File, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from datetime import datetime
from app.db.session import get_session
from app import models
import json
import os
from typing import Optional
from app.utils.utils import _wants_html, _format_seconds_readable


logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(consts.PROJECT_ROOT, "templates"))


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
async def ai_suggest_must_have_skills(data: AISuggestSkillsRequest):
    """Generate AI-suggested must-have (mandatory) skills based on job details."""
    try:
        generator = SkillGenerator()
        result = await generator.generate_must_have_skills(
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
async def ai_suggest_nice_to_have_skills(data: AISuggestSkillsRequest):
    """Generate AI-suggested nice-to-have (optional) skills based on job details."""
    try:
        generator = SkillGenerator()
        result = await generator.generate_nice_to_have_skills(
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
async def generate_job_description(
    data: GenerateJobDescriptionRequest,
    session: Session = Depends(get_session),
):
    """Generate or rewrite a comprehensive job description using AI based on details or an old JD."""
    try:
        def store_job_description_revision(
            job_id: int,
            job_description: str,
            update_parameter=None,
        ):
            existing_revisions = session.exec(
                select(models.JobDescriptionRevisions)
                .where(models.JobDescriptionRevisions.job_id == job_id)
                .order_by(models.JobDescriptionRevisions.revision_index)
            ).all()

            next_revision_index = 1
            replaced_jd_index = None
            if existing_revisions:
                next_revision_index = existing_revisions[-1].revision_index + 1

            if len(existing_revisions) >= 3:
                revisions_to_remove = existing_revisions[: len(existing_revisions) - 2]
                replaced_jd_index = revisions_to_remove[0].revision_index
                for revision in revisions_to_remove:
                    session.delete(revision)

            session.add(
                models.JobDescriptionRevisions(
                    job_id=job_id,
                    revision_index=next_revision_index,
                    job_description=job_description,
                    update_parameter=update_parameter,
                )
            )
            session.commit()
            return next_revision_index, replaced_jd_index

        generator = JobDescriptionGenerator()
        if data.old_job_description and data.update_parameter:
            allowed_parameters = {
                "Rewrite for Senior level",
                "Rewrite for Junior Level",
                "Make Concise",
                "Make more Technical",
                "Expand Responsibilities",
            }
            if data.update_parameter not in allowed_parameters:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid update_parameter.",
                )
            if not data.job_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="job_id is required for rewrite requests.",
                )

            job = session.exec(
                select(models.Jobs).where(models.Jobs.job_id == data.job_id)
            ).first()
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job not found for job_id {data.job_id}.",
                )

            result = generator.rewrite_job_description(
                old_job_description=data.old_job_description,
                update_parameter=data.update_parameter,
            )
            if result.get("success"):
                rewritten_text = result.get("rewritten_job_description", "")
                word_count = len(rewritten_text.split())
                next_revision_index, replaced_jd_index = store_job_description_revision(
                    job_id=data.job_id,
                    job_description=rewritten_text,
                    update_parameter=data.update_parameter,
                )

                return {
                    "job_description": rewritten_text,
                    "word_count": word_count,
                    "revision_index": next_revision_index,
                    "replaced_jd_index": replaced_jd_index,
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to rewrite job description: {result.get('error')}",
                )

        result = await generator.generate_job_description(
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
            word_count = len(job_description_text.split())

            if not data.job_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="job_id is required for generate requests.",
                )

            job = session.exec(
                select(models.Jobs).where(models.Jobs.job_id == data.job_id)
            ).first()
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job not found for job_id {data.job_id}.",
                )

            next_revision_index, replaced_jd_index = store_job_description_revision(
                job_id=data.job_id,
                job_description=job_description_text,
            )

            return {
                "job_description": job_description_text,
                "word_count": word_count,
                "revision_index": next_revision_index,
                "replaced_jd_index": replaced_jd_index,
            }
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


@router.get("/jobs/{job_id}/revisions", response_model=JobDescriptionRevisionsResponse)
def get_job_description_revisions(
    job_id: int,
    session: Session = Depends(get_session),
):
    try:
        rows = session.exec(
            select(models.JobDescriptionRevisions)
            .where(models.JobDescriptionRevisions.job_id == job_id)
            .order_by(models.JobDescriptionRevisions.revision_index)
        ).all()

        revisions = [
            JobDescriptionRevision(
                id=r.id,
                job_id=r.job_id,
                revision_index=r.revision_index,
                job_description=r.job_description,
                update_parameter=r.update_parameter,
                created_at=r.created_at,
            )
            for r in rows
        ]

        return JobDescriptionRevisionsResponse(
            job_id=job_id, revisions=revisions, total_revisions=len(revisions)
        )
    except Exception as e:
        logger.error(f"Error fetching JD revisions for job_id={job_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch job description revisions",
        )


@router.get("/linkedin/login")
async def linkedin_login(request: Request):
    import urllib.parse
    
    scopes = "openid profile email w_member_social"

    if not consts.LINKEDIN_CLIENT_ID or not consts.LINKEDIN_CLIENT_SECRET or not consts.LINKEDIN_REDIRECT_URI:
        error_message = "LinkedIn OAuth configuration is incomplete. Please set LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, and LINKEDIN_REDIRECT_URI in the config."
        logger.error(error_message)
        if _wants_html(request):
            return templates.TemplateResponse(
                "linkedin/callback.html",
                {
                    "request": request,
                    "title": "LinkedIn connection error",
                    "message": "LinkedIn OAuth configuration is incomplete.",
                    "details": error_message,
                    "accent": "#b42318",
                    "action_label": "Try again",
                    "name": None,
                    "expires_in": None,
                    "expires_readable": None,
                },
                status_code=500,
            )
        raise HTTPException(status_code=500, detail=error_message)
    
    auth_url = (
        "https://www.linkedin.com/oauth/v2/authorization?"
        f"response_type=code"
        f"&client_id={consts.LINKEDIN_CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(consts.LINKEDIN_REDIRECT_URI)}"
        f"&state=linkedin_auth_state"
        f"&scope={urllib.parse.quote(scopes)}"
    )
    return {"auth_url": auth_url}


@router.get("/linkedin/callback")
async def linkedin_callback(
    request: Request,
    code: str = None,
    error: str = None,
    error_description: str = None,
):
    login_url = f"{consts.ADMIN_FRONTEND}/linkedin/login"

    if error:
        if _wants_html(request):
            return templates.TemplateResponse(
                "linkedin/callback.html",
                {
                    "request": request,
                    "title": "LinkedIn connection failed",
                    "message": "LinkedIn authentication failed.",
                    "details": f"Error: " + error_description if error_description else error,
                    "accent": "#b42318",
                    "action_label": "Try again",
                    "name": None,
                    "expires_in": None,
                    "expires_readable": None,
                    "login_url": login_url,
                },
                status_code=400,
            )

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": error,
                "error_description": error_description,
                "message": "LinkedIn authentication failed.",
            },
        )
    
    if not code:
        if _wants_html(request):
            return templates.TemplateResponse(
                "linkedin/callback.html",
                {
                    "request": request,
                    "title": "LinkedIn connection failed",
                    "message": "Authorization code is missing.",
                    "details": "The callback did not include a code parameter.",
                    "accent": "#b42318",
                    "action_label": "Try again",
                    "login_url": login_url,
                    "name": None,
                    "expires_in": None,
                    "expires_readable": None,
                },
                status_code=400,
            )
        raise HTTPException(status_code=400, detail="Authorization code is missing.")
        
    try:
        import httpx
        
        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": consts.LINKEDIN_REDIRECT_URI,
            "client_id": consts.LINKEDIN_CLIENT_ID,
            "client_secret": consts.LINKEDIN_CLIENT_SECRET,
        }
        
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(token_url, data=data)
            if token_resp.status_code != 200:
                logger.error(f"Failed to fetch LinkedIn access token: {token_resp.text}")
                token_resp_json = json.loads(token_resp.text) if token_resp.text else {}
                if _wants_html(request):
                    return templates.TemplateResponse(
                        "linkedin/callback.html",
                        {
                            "request": request,
                            "title": "LinkedIn token exchange failed",
                            "message": "The authorization code could not be exchanged for an access token.",
                            "details": token_resp_json.get("error_description") if token_resp_json.get("error_description") else token_resp.text,
                            "accent": "#b42318",
                            "action_label": "Try again",
                            "name": None,
                            "expires_in": None,
                            "expires_readable": None,
                        "login_url": login_url,
                        },
                        status_code=token_resp.status_code,
                    )
                return JSONResponse(
                    status_code=token_resp.status_code,
                    content={
                        "success": False,
                        "error": "token_exchange_failed",
                        "message": "Failed to exchange authorization code for access token.",
                        "detail": token_resp.text
                    }
                )
            
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in")
            
            userinfo_url = "https://api.linkedin.com/v2/userinfo"
            userinfo_headers = {"Authorization": f"Bearer {access_token}"}
            userinfo_resp = await client.get(userinfo_url, headers=userinfo_headers)
            
            if userinfo_resp.status_code != 200:
                logger.error(f"Failed to fetch LinkedIn user info: {userinfo_resp.text}")
                if _wants_html(request):
                    return templates.TemplateResponse(
                        "linkedin/callback.html",
                        {
                            "request": request,
                            "title": "LinkedIn profile lookup failed",
                            "message": "The LinkedIn member profile could not be loaded.",
                            "details": userinfo_resp.text,
                            "accent": "#b42318",
                            "action_label": "Try again",
                            "name": None,
                            "expires_in": None,
                        "login_url": login_url,
                            "expires_readable": None,
                        },
                        status_code=userinfo_resp.status_code,
                    )
                return JSONResponse(
                    status_code=userinfo_resp.status_code,
                    content={
                        "success": False,
                        "error": "userinfo_failed",
                        "message": "Failed to retrieve member profile info from LinkedIn.",
                        "detail": userinfo_resp.text
                    }
                )
                
            userinfo_data = userinfo_resp.json()
            sub = userinfo_data.get("sub")
            name = userinfo_data.get("name")
            
            if not sub:
                if _wants_html(request):
                        return templates.TemplateResponse(
                            "linkedin/callback.html",
                            {
                                "request": request,
                                "title": "LinkedIn profile incomplete",
                                "message": "OpenID subject 'sub' was missing from the profile payload.",
                                "details": "Please retry the sign-in flow.",
                                "accent": "#b42318",
                                "action_label": "Try again",
                                "name": None,
                            "login_url": login_url,
                                "expires_in": None,
                                "expires_readable": None,
                            },
                            status_code=400,
                        )
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "missing_member_id",
                        "message": "OpenID subject 'sub' field missing in profile info.",
                    },
                )
                
            author_urn = f"urn:li:person:{sub}"
            
            token_file_path = os.path.join(consts.PROJECT_ROOT, ".linkedin_token.json")
            credentials = {
                "access_token": access_token,
                "author_urn": author_urn,
                "name": name,
                "expires_in": expires_in,
                "authenticated_at": datetime.utcnow().isoformat()
            }
            
            with open(token_file_path, "w") as f:
                json.dump(credentials, f, indent=4)
                
            logger.info(f"LinkedIn authentication successful for user: {name} ({author_urn})")
            if _wants_html(request):
                return templates.TemplateResponse(
                    "linkedin/callback.html",
                    {
                        "request": request,
                        "title": "LinkedIn connected",
                        "message": f"Authentication completed successfully for {name or 'the LinkedIn member'}.",
                        "details": "You can now close this tab and return to the admin workflow.",
                        "accent": "#067647",
                        "action_label": "Reconnect",
                        "login_url": login_url,
                        "name": name,
                        "expires_in": expires_in,
                        "expires_readable": _format_seconds_readable(expires_in),
                    },
                )
            
            return {
                "success": True,
                "message": "LinkedIn authentication successful and connected!",
                "name": name,
                "expires_in": expires_in,
                "expires_readable": _format_seconds_readable(expires_in),
            }
            
    except Exception as e:
        logger.error(f"Error in LinkedIn callback: {e}")
        traceback.print_exc()
        if _wants_html(request):
            return templates.TemplateResponse(
                "linkedin/callback.html",
                {
                    "request": request,
                    "title": "LinkedIn connection error",
                    "message": "An unexpected error occurred during authorization.",
                    "details": str(e),
                    "accent": "#b42318",
                    "action_label": "Try again",
                    "login_url": login_url,
                    "name": None,
                    "expires_in": None,
                },
                status_code=500,
            )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "unexpected_error",
                "message": "An unexpected error occurred during authorization.",
                "detail": str(e),
            },
        )


@router.post("/linkedin/post")
async def post_to_linkedin(
    text: str = Form(...),
    image: Optional[UploadFile] = File(None)
):
    import httpx
    
    token_file_path = os.path.join(consts.PROJECT_ROOT, ".linkedin_token.json")
    if not os.path.exists(token_file_path):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="LinkedIn credentials not found. Please log in first."
        )
        
    try:
        with open(token_file_path, "r") as f:
            credentials = json.load(f)
            
        access_token = credentials.get("access_token")
        author_urn = credentials.get("author_urn")
        
        if not access_token or not author_urn:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials stored. Please re-authenticate."
            )
            
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202605",
            "Content-Type": "application/json"
        }
        
        image_urn = None
        
        if image:
            init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
            init_payload = {
                "initializeUploadRequest": {
                    "owner": author_urn
                }
            }
            
            async with httpx.AsyncClient() as client:
                init_resp = await client.post(init_url, headers=headers, json=init_payload)
                if init_resp.status_code != 200:
                    logger.error(f"LinkedIn image upload initialization failed: {init_resp.text}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to initialize image upload: {init_resp.text}"
                    )
                    
                init_data = init_resp.json()
                value_data = init_data.get("value", {})
                upload_url = value_data.get("uploadUrl")
                image_urn = value_data.get("image")
                
                if not upload_url or not image_urn:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="LinkedIn response missing uploadUrl or image URN."
                    )
                    
                image_content = await image.read()
                upload_headers = {
                    "Content-Type": image.content_type or "image/jpeg"
                }
                upload_resp = await client.put(upload_url, headers=upload_headers, content=image_content)
                if upload_resp.status_code not in (200, 201):
                    logger.error(f"LinkedIn image binary upload failed: {upload_resp.text}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to upload binary image data: {upload_resp.text}"
                    )
                    
        post_url = "https://api.linkedin.com/rest/posts"
        
        post_payload = {
            "author": author_urn,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED"
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }
        
        if image_urn:
            post_payload["content"] = {
                "media": {
                    "id": image_urn
                }
            }
            
        async with httpx.AsyncClient() as client:
            post_resp = await client.post(post_url, headers=headers, json=post_payload)
            if post_resp.status_code not in (200, 201):
                logger.error(f"LinkedIn post creation failed: {post_resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to publish post to LinkedIn: {post_resp.text}"
                )
                
            post_id = post_resp.headers.get("x-restli-id")
            post_link = f"https://www.linkedin.com/feed/update/{post_id}" if post_id else None
            
            return {
                "success": True,
                "message": "Job post successfully published to LinkedIn!",
                "post_id": post_id,
                "post_link": post_link,
                "author": author_urn,
                "has_image": bool(image_urn),
                "image_urn": image_urn
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error posting to LinkedIn: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while posting to LinkedIn: {str(e)}"
        )

