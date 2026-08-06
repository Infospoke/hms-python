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
from app.schemas import OfferLetterRequest, RegenerateOfferLetterRequest
from app.services.offer_service import get_offer_details
from app.services.reports.offer_letter_report import generate_offer_letter_pdf


logger = logging.getLogger(__name__)

router = APIRouter()

def build_offer_letter_filename(candidate_id=None, offer_id=None, candidate_name=None, base_pdf_name="Offer_Letter.pdf") -> str:
    from datetime import datetime
    year_str = str(datetime.now().year)

    cid_str = str(candidate_id).strip() if candidate_id is not None else ""
    if cid_str:
        if cid_str.isdigit():
            formatted_cid = f"{int(cid_str):04d}"
            cid_part = f"CID-{year_str}-{formatted_cid}"
        else:
            if cid_str.upper().startswith("CID-"):
                cid_part = cid_str
            elif cid_str.startswith(f"{year_str}-"):
                cid_part = f"CID-{cid_str}"
            else:
                cid_part = f"CID-{year_str}-{cid_str}"
    else:
        cid_part = f"CID-{year_str}-0000"

    off_str = str(offer_id).strip() if offer_id is not None else "0"
    cname_str = (candidate_name or "Candidate").strip().replace(" ", "_")

    clean_pdf_name = (base_pdf_name or "Offer_Letter.pdf").strip()
    if clean_pdf_name.endswith(".pdf"):
        clean_pdf_name = clean_pdf_name[:-4]
    if "_" in clean_pdf_name and "Offer_Letter" in clean_pdf_name:
        clean_pdf_name = "Offer_Letter"
    clean_pdf_name = f"{clean_pdf_name}.pdf"

    # Format: CID-{year}-{candidate_id}-{offer_id}-{candidate_name}-{pdfname}
    return f"{cid_part}-{off_str}-{cname_str}-{clean_pdf_name}"


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
        data = get_offer_details(db, request, force_budget_ctc=True)

        # Generate the PDF
        pdf_buffer = generate_offer_letter_pdf(data)
        pdf_bytes = pdf_buffer.getvalue()

        # Create filename in format CID-{candidate_id}-{offer_id}-{candidate_name}-{pdfname}
        candidate_name = data.get("candidate_name", "Candidate")
        cand_id = request.candidate_id or request.application_id
        off_id = request.offer_id or data.get("offer_id") or request.application_id

        filename = build_offer_letter_filename(
            candidate_id=cand_id,
            offer_id=off_id,
            candidate_name=candidate_name,
            base_pdf_name=f"{candidate_name.replace(' ', '_')}_Offer_Letter.pdf"
        )

        # Upload to MinIO (directly in offer-letters/ without application_id subfolder)
        from app.services import minio_helper
        object_name = f"offer-letters/{filename}"
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

@router.post("/regenerate-offer-letter")
def regenerate_offer_letter(
    request: RegenerateOfferLetterRequest,
    db: Session = Depends(deps.get_session)
):
    try:
        import io
        from app.services import minio_helper
        from app.services.reports.offer_letter_report import generate_offer_letter_pdf
        from datetime import datetime

        # 1. Update OfferDetails in database with new total_ctc
        probation_period = None
        try:
            offer_detail = db.exec(
                select(models.OfferDetails).where(
                    (models.OfferDetails.id == request.offer_id) |
                    (models.OfferDetails.job_application_id == request.application_id)
                )
            ).first()

            if offer_detail:
                probation_period = offer_detail.probation_period

            status_str = "Regenerated" if request.approve else "Rejected"
            if offer_detail:
                offer_detail.offer_status = status_str
                offer_detail.approve = request.approve
                offer_detail.reject = not request.approve
                offer_detail.responded_at = datetime.now()
                offer_detail.total_ctc = int(request.total_ctc)
                db.add(offer_detail)
            else:
                new_offer_detail = models.OfferDetails(
                    id=request.offer_id,
                    job_application_id=request.application_id,
                    offer_status=status_str,
                    approve=request.approve,
                    reject=not request.approve,
                    probation_period=None,
                    total_ctc=int(request.total_ctc),
                    responded_at=datetime.now()
                )
                db.add(new_offer_detail)

            # Also update BudgetCompensation.annual_hiring_cost
            candidate = db.exec(
                select(models.JobApplications).where(models.JobApplications.id == request.application_id)
            ).first()
            if candidate and candidate.job_id:
                from app.models import CreateJobDetails, BudgetCompensation
                job = db.exec(select(CreateJobDetails).where(CreateJobDetails.job_id == candidate.job_id)).first()
                if job and job.sr_id:
                    budget = db.exec(select(BudgetCompensation).where(BudgetCompensation.sr_id == job.sr_id)).first()
                    if budget:
                        budget.annual_hiring_cost = int(request.total_ctc)
                        db.add(budget)

            db.commit()
        except Exception as db_err:
            print(f"Warning: Failed to update OfferDetails in database during regenerate: {db_err}")
            try:
                db.rollback()
            except Exception:
                pass

        # If rejected, return JSON response
        if not request.approve:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "Rejected",
                    "offer_status": "Rejected",
                    "message": "Regenerate offer rejected"
                }
            )

        # 2. Get Job Application & Candidate Details
        candidate = db.exec(
            select(models.JobApplications).where(models.JobApplications.id == request.application_id)
        ).first()

        candidate_name = "Candidate"
        if candidate:
            names = [n for n in [candidate.first_name, candidate.last_name] if n]
            if names:
                candidate_name = " ".join(names)

        # Calculate CTC salary components based on total_ctc
        ctc_val = float(request.total_ctc or 0.0)
        basic_salary = ctc_val * 0.5 if ctc_val > 0 else 0.0

        from app.services.offer_service import generate_reference_id
        offer_data = {
            "reference_id": generate_reference_id(request.application_id),
            "date": datetime.now().strftime("%d-%m-%Y"),
            "candidate_name": candidate_name,
            "job_title": getattr(candidate, "current_stage", "Employee") if candidate else "Employee",
            "reporting_manager": "Manager",
            "ctc": ctc_val,
            "basic_salary": basic_salary,
            "signing_bonus": 0.0,
            "equity_rsu": 0.0,
            "other_benefits": ctc_val - basic_salary if ctc_val > basic_salary else 0.0,
            "notice_period": "30 Days",
            "probation_period": probation_period
        }

        # 3. Generate updated PDF
        pdf_buffer = generate_offer_letter_pdf(offer_data)
        pdf_bytes = pdf_buffer.getvalue()

        # 4. Construct MinIO filename
        filename = build_offer_letter_filename(
            candidate_id=request.candidate_id,
            offer_id=request.offer_id,
            candidate_name=candidate_name,
            base_pdf_name=f"{candidate_name.replace(' ', '_')}_Offer_Letter.pdf"
        )
        object_name = f"offer-letters/{filename}"

        # 5. Overwrite / Upload regenerated PDF to MinIO
        upload_result = minio_helper.upload_pdf(pdf_bytes, object_name)
        if not upload_result.get("success"):
            print(f"Warning: Failed to upload regenerated offer letter to MinIO: {upload_result.get('error')}")

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
        logger.error(f"Failed to regenerate offer letter: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to regenerate offer letter: {e}")

from pydantic import BaseModel
from typing import Optional

from fastapi import Form, File, UploadFile

@router.post("/approved-offer")
def approved_offer(
    application_id: Optional[str] = Form(None),
    candidate_id: Optional[str] = Form(None),
    offer_id: Optional[str] = Form(None),
    approve: bool = Form(...),
    comments: Optional[str] = Form(None),
    signature: Optional[UploadFile] = File(None),
    signature_type: Optional[str] = Form(None),
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

            if offer_detail:
                offer_detail.approve = approve
                offer_detail.reject = not approve
                offer_detail.responded_at = datetime.now()
                session.add(offer_detail)
            else:
                new_offer_detail = models.OfferDetails(
                    job_application_id=app_id_int,
                    approve=approve,
                    reject=not approve,
                    responded_at=datetime.now()
                )
                session.add(new_offer_detail)

            session.commit()
        except Exception as db_err:
            print(f"Warning: Failed to update OfferDetails in database: {db_err}")
            try:
                session.rollback()
            except Exception:
                pass

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

        eff_cand_id = candidate_id or application_id
        eff_offer_id = offer_id or application_id

        # Fetch candidate name from DB to construct exact filename
        candidate_name = "Candidate"
        try:
            raw_cid = str(eff_cand_id).replace("CID-", "").split("-")[-1]
            lookup_id = int(raw_cid) if raw_cid.isdigit() else int(application_id)
            job_app = session.exec(
                select(models.JobApplications).where(models.JobApplications.id == lookup_id)
            ).first()
            if job_app:
                names = [n for n in [job_app.first_name, job_app.last_name] if n]
                if names:
                    candidate_name = " ".join(names)
        except Exception as e:
            print(f"Could not fetch candidate name: {e}")

        cand_filename = build_offer_letter_filename(
            candidate_id=eff_cand_id,
            offer_id=eff_offer_id,
            candidate_name=candidate_name,
            base_pdf_name=f"{candidate_name.replace(' ', '_')}_Offer_Letter.pdf"
        )
        object_name = f"offer-letters/{cand_filename}"

        minio_client = minio_helper.get_minio_client()
        pdf_bytes = None

        # Get existing offer letter PDF from MinIO (direct file in offer-letters/)
        try:
            response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, object_name)
            pdf_bytes = response.read()
            response.close()
            response.release_conn()
        except Exception:
            # Fallback 1: Search direct PDF files in offer-letters/
            try:
                objects = minio_client.list_objects(consts.INFOSPOKE_S3_BUCKET_NAME, prefix="offer-letters/")
                for obj in objects:
                    oname = obj.object_name
                    if oname.endswith('.pdf') and ("/" not in oname[14:]):
                        if candidate_name.replace(' ', '_').lower() in oname.lower() or str(application_id) in oname:
                            response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, oname)
                            pdf_bytes = response.read()
                            response.close()
                            response.release_conn()
                            object_name = oname
                            break
            except Exception:
                pass

        # Fallback 3: Pick any existing PDF in offer-letters/
        if not pdf_bytes:
            try:
                objects = minio_client.list_objects(consts.INFOSPOKE_S3_BUCKET_NAME, prefix="offer-letters/", recursive=True)
                for obj in objects:
                    if obj.object_name.endswith('.pdf'):
                        response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, obj.object_name)
                        pdf_bytes = response.read()
                        response.close()
                        response.release_conn()
                        object_name = obj.object_name
                        break
            except Exception:
                pass

        if not pdf_bytes:
            raise HTTPException(status_code=404, detail=f"Offer letter PDF not found for applicant {application_id}")

        # Extract company signature base64 if uploaded
        import base64
        signature_b64 = None
        if signature and hasattr(signature, "file"):
            sig_bytes = signature.file.read()
            if sig_bytes:
                signature_b64 = base64.b64encode(sig_bytes).decode('utf-8')

        effective_sig_text = signature_type.strip() if (signature_type and str(signature_type).strip()) else None

        approved_date = datetime.now().strftime("%d-%m-%Y")
        if signature_b64 or effective_sig_text:
            pdf_bytes = add_signature_to_pdf(
                original_pdf_bytes=pdf_bytes,
                accepted_date=approved_date,
                signature_base64=signature_b64,
                signature_text=effective_sig_text,
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
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
        return JSONResponse(
            status_code=200,
            content={
                "status": "Successfully approved offer",
                "path": object_name,
                "pdf": pdf_b64,
            }
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
    candidate_id: Optional[str] = Form(None),
    offer_id: Optional[str] = Form(None),
    approve: bool = Form(...),
    comments: Optional[str] = Form(None),
    signature: Optional[UploadFile] = File(None),
    signature_type: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    return process_offer_action(
        application_id=application_id,
        candidate_id=candidate_id,
        offer_id=offer_id,
        approve=approve,
        comments=comments,
        signature=signature,
        signature_type=signature_type,
        session=session
    )

def process_offer_action(
    application_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    offer_id: Optional[str] = None,
    approve: bool = True,
    comments: Optional[str] = None,
    signature: Optional[UploadFile] = None,
    signature_type: Optional[str] = None,
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

            status_str = "Accepted" if approve else "Rejected"
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
            try:
                session.rollback()
            except Exception:
                pass

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

        eff_cand_id = candidate_id or final_applicant_id
        eff_offer_id = offer_id or final_applicant_id

        # Get candidate name from DB
        candidate_name = "Candidate"
        try:
            raw_cid = str(eff_cand_id).replace("CID-", "").split("-")[-1]
            lookup_id = int(raw_cid) if raw_cid.isdigit() else int(final_applicant_id)
            job_app = session.exec(
                select(models.JobApplications).where(models.JobApplications.id == lookup_id)
            ).first()
            if job_app:
                names = [n for n in [job_app.first_name, job_app.last_name] if n]
                if names:
                    candidate_name = " ".join(names)
        except Exception as e:
            print(f"Could not fetch candidate name: {e}")

        cand_filename = build_offer_letter_filename(
            candidate_id=eff_cand_id,
            offer_id=eff_offer_id,
            candidate_name=candidate_name,
            base_pdf_name=f"{candidate_name.replace(' ', '_')}_Offer_Letter.pdf"
        )
        object_name = f"offer-letters/{cand_filename}"

        # Get existing PDF from MinIO (direct file in offer-letters/)
        minio_client = minio_helper.get_minio_client()
        original_pdf_bytes = None
        try:
            response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, object_name)
            original_pdf_bytes = response.read()
            response.close()
            response.release_conn()
        except Exception:
            # Fallback 1: Search direct PDF files in offer-letters/
            try:
                objects = minio_client.list_objects(consts.INFOSPOKE_S3_BUCKET_NAME, prefix="offer-letters/")
                for obj in objects:
                    oname = obj.object_name
                    if oname.endswith('.pdf') and ("/" not in oname[14:]):
                        if candidate_name.replace(' ', '_').lower() in oname.lower() or str(final_applicant_id) in oname:
                            response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, oname)
                            original_pdf_bytes = response.read()
                            response.close()
                            response.release_conn()
                            object_name = oname
                            break
            except Exception:
                pass

        # Fallback 3: Pick any existing PDF in offer-letters/
        if not original_pdf_bytes:
            try:
                objects = minio_client.list_objects(consts.INFOSPOKE_S3_BUCKET_NAME, prefix="offer-letters/", recursive=True)
                for obj in objects:
                    if obj.object_name.endswith('.pdf'):
                        response = minio_client.get_object(consts.INFOSPOKE_S3_BUCKET_NAME, obj.object_name)
                        original_pdf_bytes = response.read()
                        response.close()
                        response.release_conn()
                        object_name = obj.object_name
                        break
            except Exception:
                pass

        if not original_pdf_bytes:
            raise HTTPException(status_code=404, detail=f"Offer letter PDF not found for applicant {final_applicant_id}")

        # Extract signature base64 if a file was uploaded
        import base64
        signature_b64 = None
        if signature and hasattr(signature, "file"):
            sig_bytes = signature.file.read()
            if sig_bytes:
                signature_b64 = base64.b64encode(sig_bytes).decode('utf-8')

        effective_sig_text = signature_type.strip() if (signature_type and str(signature_type).strip()) else None

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
            "Access-Control-Expose-Headers": "Content-Disposition",
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
