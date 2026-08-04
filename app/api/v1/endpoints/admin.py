import logging
import traceback
from fastapi import APIRouter, HTTPException, status, Response, Query
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

from app.utils.groq_api import call_llm
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
from app.api import deps
from app.schemas import OfferLetterRequest
from app.services.offer_service import get_offer_details
from app.services.reports.offer_letter_report import generate_offer_letter_pdf


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

            result = await generator.rewrite_job_description(
                old_job_description=data.old_job_description,
                update_parameter=data.update_parameter
            )
            if result.get("success"):
                rewritten_jd = result.get("job_description", {})
                return JSONResponse(content=rewritten_jd)
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
            languages=data.languages
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
    try:
        benchmarks = await fetch_salary_benchmarks(
            job_title=req.job_title,
            location=req.location,
            employment_type=req.employment_type,
            seniority=req.seniority,
        )
    except Exception as e:
        logger.warning(f"Live market salary API failed: {e}")
        benchmarks = []

    if benchmarks and len(benchmarks) > 0:
        first = benchmarks[0]
        min_sal = first.min_salary or 300000.0
        max_sal = first.max_salary or 500000.0
        return CTCReviewResponse(min_salary=float(min_sal), max_salary=float(max_sal))

    # Fallback to ultra-fast Groq model estimation for localized CTC range
    prompt = f"""You are a recruitment compensation analyst specializing in the Indian tech market.
Estimate a highly realistic annual salary range (CTC in INR) for the following job profile:
- Job Title: {req.job_title}
- Department: {req.department}
- Seniority: {req.seniority.value}
- Location: {req.location}
- Employment Type: {req.employment_type}

Ensure the numbers are realistic for the specified Indian location and seniority level (e.g. 800000 to 1500000).
Respond with a JSON object in this exact format:
{{
  "min_salary": 800000,
  "max_salary": 1500000
}}
"""
    try:
        llm_resp = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
        min_sal = float(llm_resp.get("min_salary", 300000))
        max_sal = float(llm_resp.get("max_salary", 500000))
        return CTCReviewResponse(min_salary=min_sal, max_salary=max_sal)
    except Exception as e:
        logger.error(f"Failed to suggest CTC via LLM: {e}")
        return CTCReviewResponse(min_salary=300000.0, max_salary=500000.0)


@router.post("/certifications-suggestions", response_model=CertificationsResponse)
async def get_certifications_suggestions(req: JobRequirementsRequest):
    prompt = build_certifications_prompt(req)

    try:
        llm_resp = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
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
        llm_resp = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
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
        llm_resp = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
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

@router.post("/generate-offer-letter")
def generate_offer_letter(
    request: OfferLetterRequest,
    db: Session = Depends(deps.get_session)
):
    try:
        # Fetch the JSON data
        data = get_offer_details(db, request)

        # Generate the PDF
        pdf_buffer = generate_offer_letter_pdf(data)
        pdf_bytes = pdf_buffer.getvalue()

        # Create filename
        candidate_name = data.get("candidate_name", "Candidate").replace(" ", "_")
        filename = f"{candidate_name}_Offer_Letter.pdf"

        # Upload to MinIO
        from app.services import minio_helper
        object_name = f"offer-letters/{request.application_id}/{filename}"
        upload_result = minio_helper.upload_pdf(pdf_bytes, object_name)
        if not upload_result.get("success"):
            print(f"Warning: Failed to upload offer letter to MinIO: {upload_result.get('error')}")

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers=headers,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

from pydantic import BaseModel
from typing import Optional

from fastapi import Form, File, UploadFile

@router.post("/approved-offer")
def accept_offer(
    application_id: Optional[str] = Form(None),
    approve: bool = Form(...),
    comments: Optional[str] = Form(None),
    signature: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session)
):
    try:
        import io
        from app.services import minio_helper
        from app.services.reports.offer_letter_report import add_signature_to_pdf
        from datetime import datetime

        if not application_id:
            raise HTTPException(status_code=400, detail="application_id is required")

        # Update OfferDetails status in database
        try:
            app_id_int = int(application_id)
            offer_detail = session.exec(
                select(models.OfferDetails).where(
                    (models.OfferDetails.job_application_id == app_id_int) | 
                    (models.OfferDetails.id == app_id_int)
                )
            ).first()

            status_str = "Approved" if approve else "Rejected"
            if offer_detail:
                offer_detail.offer_status = status_str
                offer_detail.approve = approve
                offer_detail.reject = not approve
                offer_detail.responded_at = datetime.now()
                session.add(offer_detail)
            else:
                new_offer_detail = models.OfferDetails(
                    job_application_id=app_id_int,
                    offer_status=status_str,
                    approve=approve,
                    reject=not approve,
                    responded_at=datetime.now()
                )
                session.add(new_offer_detail)

            session.commit()
        except Exception as db_err:
            print(f"Warning: Failed to update OfferDetails in database: {db_err}")

        # If offer is rejected, return JSON response
        if not approve:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "Rejected",
                    "offer_status": "Rejected",
                    "message": "Offer rejected successfully"
                }
            )

        # Get existing offer letter PDF from MinIO
        minio_client = minio_helper.get_minio_client()
        object_name = f"offer-letters/{application_id}/Naidu_Kunapareddy_Offer_Letter.pdf"
        
        try:
            response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, object_name)
            pdf_bytes = response.read()
            response.close()
            response.release_conn()
        except Exception as e:
            objects = minio_client.list_objects(consts.INFOSPOKE_S3_BUCKET_NAME, prefix=f"offer-letters/{application_id}/")
            found = False
            for obj in objects:
                if obj.object_name.endswith('.pdf'):
                    object_name = obj.object_name
                    response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, object_name)
                    pdf_bytes = response.read()
                    response.close()
                    response.release_conn()
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=404, detail=f"Offer letter PDF not found for applicant {application_id}")

        # Extract company signature base64 if uploaded
        import base64
        signature_b64 = None
        if signature and hasattr(signature, "file"):
            sig_bytes = signature.file.read()
            if sig_bytes:
                signature_b64 = base64.b64encode(sig_bytes).decode('utf-8')

        approved_date = datetime.now().strftime("%d-%m-%Y")
        if signature_b64:
            pdf_bytes = add_signature_to_pdf(
                original_pdf_bytes=pdf_bytes,
                accepted_date=approved_date,
                signature_base64=signature_b64,
                is_company_signature=True
            )
            # Save signed PDF back to MinIO
            minio_client.put_object(
                consts.INFOSPOKE_S3_BUCKET_NAME,
                object_name,
                data=io.BytesIO(pdf_bytes),
                length=len(pdf_bytes),
                content_type="application/pdf"
            )

        filename = object_name.split("/")[-1]
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition, X-Offer-Status, X-Status, status",
            "X-Offer-Status": "Approved",
            "X-Status": "success",
            "status": "success",
        }
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve offer: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to approve offer: {e}")

@router.post("/accept-offer")
def accept_offer(
    application_id: Optional[str] = Form(None),
    approve: bool = Form(...),
    comments: Optional[str] = Form(None),
    signature: Optional[UploadFile] = File(None),
    signature_text: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    return process_offer_action(
        application_id=application_id,
        approve=approve,
        comments=comments,
        signature=signature,
        signature_text=signature_text,
        session=session
    )

def process_offer_action(
    application_id: Optional[str] = None,
    approve: bool = True,
    comments: Optional[str] = None,
    signature: Optional[UploadFile] = None,
    signature_text: Optional[str] = None,
    session: Session = None
):
    try:
        import io
        from app.services import minio_helper
        from app.services.reports.offer_letter_report import add_signature_to_pdf
        from datetime import datetime

        final_applicant_id = application_id
        if not final_applicant_id:
            raise HTTPException(status_code=400, detail="application_id is required")

        # Update OfferDetails status in database
        try:
            app_id_int = int(final_applicant_id)
            
            # 1. Update/Create OfferDetails
            offer_detail = session.exec(
                select(models.OfferDetails).where(
                    (models.OfferDetails.job_application_id == app_id_int) | 
                    (models.OfferDetails.id == app_id_int)
                )
            ).first()

            status_str = "Approved" if approve else "Rejected"
            if offer_detail:
                offer_detail.offer_status = status_str
                offer_detail.approve = approve
                offer_detail.reject = not approve
                offer_detail.responded_at = datetime.now()
                session.add(offer_detail)
            else:
                new_offer_detail = models.OfferDetails(
                    job_application_id=app_id_int,
                    offer_status=status_str,
                    approve=approve,
                    reject=not approve,
                    responded_at=datetime.now()
                )
                session.add(new_offer_detail)

            session.commit()
        except Exception as db_err:
            print(f"Warning: Failed to update OfferDetails in database: {db_err}")

        # If offer is rejected, return JSON response immediately
        if not approve:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "Rejected",
                    "offer_status": "Rejected",
                    "message": "Offer rejected successfully"
                }
            )

        # Get candidate name from DB
        candidate_name = "Candidate"
        try:
            app_id_int = int(final_applicant_id)
            job_app = session.exec(
                select(models.JobApplications).where(models.JobApplications.id == app_id_int)
            ).first()
            if job_app:
                names = [n for n in [job_app.first_name, job_app.last_name] if n]
                if names:
                    candidate_name = " ".join(names)
        except Exception as e:
            print(f"Could not fetch candidate name: {e}")

        # Get existing PDF from MinIO
        minio_client = minio_helper.get_minio_client()
        object_name = f"offer-letters/{final_applicant_id}/Naidu_Kunapareddy_Offer_Letter.pdf"
        
        try:
            response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, object_name)
            original_pdf_bytes = response.read()
            response.close()
            response.release_conn()
        except Exception as e:
            # Fallback search for any PDF in that folder
            objects = minio_client.list_objects(consts.INFOSPOKE_S3_BUCKET_NAME, prefix=f"offer-letters/{final_applicant_id}/")
            found = False
            for obj in objects:
                if obj.object_name.endswith('.pdf'):
                    object_name = obj.object_name
                    response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, object_name)
                    original_pdf_bytes = response.read()
                    response.close()
                    response.release_conn()
                    found = True
                    break
            if not found:
                raise HTTPException(status_code=404, detail=f"Offer letter PDF not found for applicant {final_applicant_id}")

        # Extract signature base64 if a file was uploaded
        import base64
        signature_b64 = None
        if signature and hasattr(signature, "file"):
            sig_bytes = signature.file.read()
            if sig_bytes:
                signature_b64 = base64.b64encode(sig_bytes).decode('utf-8')

        effective_sig_text = signature_text.strip() if (signature_text and signature_text.strip()) else None

        # Apply signature overlay only if a signature file or typed text is provided
        if signature_b64 or effective_sig_text:
            signed_pdf_bytes = add_signature_to_pdf(
                original_pdf_bytes=original_pdf_bytes,
                candidate_name=candidate_name,
                signature_base64=signature_b64,
                signature_text=effective_sig_text
            )

            # Upload signed PDF back to MinIO
            minio_client.put_object(
                consts.INFOSPOKE_S3_BUCKET_NAME,
                object_name,
                data=io.BytesIO(signed_pdf_bytes),
                length=len(signed_pdf_bytes),
                content_type="application/pdf"
            )
        else:
            signed_pdf_bytes = original_pdf_bytes
        
        filename = object_name.split("/")[-1]
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition, X-Offer-Status, X-Status, status",
            "X-Offer-Status": "Approved",
            "X-Status": "success",
            "status": "success",
        }
        return StreamingResponse(
            io.BytesIO(signed_pdf_bytes),
            media_type="application/pdf",
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch/update PDF with signature: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to add signature to PDF: {e}")

import time
JOB_TITLE_CACHE = {}
CACHE_TTL = 300  # 5 minutes in seconds

@router.get("/job-titles/live-search")
def live_search_job_titles(
    q: str = Query("", description="Search query for job titles"),
    session: Session = Depends(deps.get_session)
):
    query = q.strip().lower()
    results = []
    
    if query:
        # Check cache to remove continuous hitting
        if query in JOB_TITLE_CACHE:
            timestamp, cached_results = JOB_TITLE_CACHE[query]
            if time.time() - timestamp < CACHE_TTL:
                return JSONResponse({"results": cached_results})
        
        # Dynamic search using ilike
        search_results = session.exec(
            select(models.JobTitles)
            .where(models.JobTitles.job_title.ilike(f"%{query}%"))
            .order_by(models.JobTitles.id)
            .limit(15)
        ).all()
        
        for result in search_results:
            results.append({
                "id": result.id,
                "job_title": result.job_title
            })
            
        # Store in cache
        JOB_TITLE_CACHE[query] = (time.time(), results)
        
        # Simple cache cleanup if it grows too large to prevent memory leak
        if len(JOB_TITLE_CACHE) > 1000:
            JOB_TITLE_CACHE.clear()
            JOB_TITLE_CACHE[query] = (time.time(), results)
            
    return JSONResponse({"results": results})
