from typing import List, Optional, Any, Dict
from datetime import datetime
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Body,
    Query,
    status,
    BackgroundTasks,
)
from sqlmodel import Session, select, delete
from sqlalchemy import asc, desc, case
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from fastapi.responses import StreamingResponse
from app.services.reports.job_applicants_report import generate_applicants_pdf
from app.models import JobApplications, ResumeAnalysis, InterviewAnalysis
from app import models
from app.api import deps
from app.core.exceptions import ResourceNotFoundException
from app.schemas import (
    AnalyseResumesByJobIdRequest,
    ResumeBatch,
    ResumeAnalysisResponse,
    ResumeAnalysisRequest,
    DeleteResumeLogRequest,
    DeleteResumeLogsRequest,
)
from app.services.resume_parser.batch_analyzer import BatchAnalyzer
from app.core import config as consts
from app.utils import timezone_utils
from math import ceil
import traceback

router = APIRouter()


@router.post("/analysis", response_model=ResumeAnalysisResponse)
def fetch_resume_analysis(
    application_id: Optional[int] = None,
    request: Optional[ResumeAnalysisRequest] = Body(ResumeAnalysisRequest()),
    page: int = Query(consts.DEFAULT_PAGE, ge=1),
    limit: int = Query(consts.DEFAULT_LIMIT, ge=1),
    session: Session = Depends(deps.get_session),
):
    try:
        score = request.score or 0
        experience = request.experience or []
        recommendation = request.recommendation or []
        sort_by = request.sort_by or consts.DEFAULT_SORT_BY
        sort_order = request.sort_order or consts.DEFAULT_SORT_ORDER
        experience = [e.label for e in experience if e.checked]
        recommendation = [r.label.upper() for r in recommendation if r.checked]
        if "ALL RECOMMENDATIONS" in recommendation:
            recommendation = ["HIRE", "CONSIDER", "REJECT"]
        if "All Levels" in experience:
            experience = ["Beginner", "Intermediate", "Experienced"]
        query = select(models.ResumeAnalysis)
        if application_id is not None:
            query = query.where(models.ResumeAnalysis.application_id == application_id)
        else:
            if score > 0:
                query = query.where(models.ResumeAnalysis.final_score >= score)
            if experience:
                query = query.where(
                    models.ResumeAnalysis.experience_level.in_(experience)
                )
            if recommendation:
                query = query.where(
                    models.ResumeAnalysis.recommendation_decision.in_(recommendation)
                )
            sort_map = {
                "score": models.ResumeAnalysis.final_score,
                "experience": models.ResumeAnalysis.experience_level,
                "recommendation": models.ResumeAnalysis.recommendation_decision,
            }
            sort_column = sort_map.get(sort_by)
            if not sort_column:
                sort_column = getattr(models.ResumeAnalysis, sort_by, None)
            if sort_column:
                if sort_by == "experience":
                    order_case = case(
                        (
                            (sort_column == "Beginner", 1),
                            (sort_column == "Intermediate", 2),
                            (sort_column == "Experienced", 3),
                        ),
                        else_=4,
                    )
                    query = query.order_by(
                        asc(order_case) if sort_order == "asc" else desc(order_case)
                    )
                elif sort_by == "recommendation":
                    order_case = case(
                        (
                            (sort_column == "REJECT", 1),
                            (sort_column == "CONSIDER", 2),
                            (sort_column == "HIRE", 3),
                        ),
                        else_=4,
                    )
                    query = query.order_by(
                        asc(order_case) if sort_order == "asc" else desc(order_case)
                    )
                else:
                    query = query.order_by(
                        asc(sort_column) if sort_order == "asc" else desc(sort_column)
                    )
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)
        # results = [obj.model_dump() for obj in session.exec(query).all()]
        results_db = session.exec(query).all()
        results = [obj.model_dump() for obj in results_db]
        for result in results:
            for key, value in result.items():
                if isinstance(value, datetime):
                    result[key] = timezone_utils.format_datetime_for_api(value)

        results = add_interview_details(results_db, session)

        from sqlalchemy import func

        total_candidates = session.exec(
            select(func.count(models.JobApplications.id))
        ).one()
        all_results = session.exec(select(models.ResumeAnalysis)).all()
        total_pages = ceil(len(all_results) / consts.DEFAULT_LIMIT)
        response = calculate_stats(
            all_results, results, total_candidates, page, total_pages
        )
        return response
    except HTTPException:
        raise
    except (SQLAlchemyError, OperationalError) as e:
        print("ERROR:", repr(e))
        raise HTTPException(status_code=500, detail=consts.DATABASE_OPERATION_FAILED)
    # except Exception as e:
    #     raise HTTPException(status_code=500, detail=consts.INTERNAL_SERVER_ERROR)
    except Exception as e:
        print("🔥 ERROR:", str(e))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))  # temporary for debugging


@router.post("/analysis/update")
def fetch_resume_analysis_update(
    application_id: Optional[int] = Query(None),
    request_data: Optional[Dict[str, Any]] = Body(None),
    session: Session = Depends(deps.get_session),
):
    try:
        def format_resume_update(item: models.ResumeAnalysisUpdate) -> Dict[str, Any]:
            res = item.model_dump()
            for key, value in res.items():
                if isinstance(value, datetime):
                    res[key] = timezone_utils.format_datetime_for_api(value)
            
            import json
            
            # Fetch the associated ResumeAnalysis record for basic stats
            resume_analysis = session.exec(
                select(models.ResumeAnalysis).where(
                    models.ResumeAnalysis.application_id == item.application_id
                )
            ).first()
            
            # Fetch raw JSON to extract more specific LLM fields
            resume_attr = session.exec(
                select(models.ResumeAttributes).where(
                    models.ResumeAttributes.application_id == item.application_id
                )
            ).first()
            
            raw_analysis = {}
            if resume_attr and resume_attr.analysis_json:
                try:
                    raw_analysis = json.loads(resume_attr.analysis_json)
                except Exception:
                    pass
            
            # Extract relevant_experience_years safely
            relevant_exp_val = (
                raw_analysis.get("relevant_experience_years")
                or raw_analysis.get("analysis", {}).get("relevant_experience_years")
            )
            
            # Extract total_jobs_count safely
            total_jobs_val = (
                raw_analysis.get("total_jobs_count")
                or raw_analysis.get("analysis", {}).get("total_jobs_count")
                or (resume_analysis.total_jobs_count if resume_analysis else None)
            )
            
            # Extract average tenure safely
            average_tenure_val = (
                raw_analysis.get("average_job_change")
                or raw_analysis.get("job_analysis", {}).get("average_job_change")
                or (resume_analysis.average_job_change if resume_analysis else None)
            )
            
            relevant_exp_str = "Not Mentioned"
            if relevant_exp_val is not None:
                try:
                    relevant_exp_str = f"{int(float(relevant_exp_val))} Year(s)"
                except Exception:
                    relevant_exp_str = str(relevant_exp_val)
                    
            companies_worked_str = "Not Mentioned"
            if total_jobs_val is not None:
                companies_worked_str = str(total_jobs_val)
                
            average_tenure_str = "Not Mentioned"
            if average_tenure_val:
                average_tenure_str = str(average_tenure_val)

            total_exp_str = res.get("total_experience") or "Not Mentioned"
            
            def clean_description(desc):
                if not desc:
                    return ""
                if isinstance(desc, list):
                    desc = "\n".join([str(d) for d in desc])
                if isinstance(desc, str):
                    # Clean up encoding issue like â€¢ and normal bullet signs
                    cleaned = desc.replace("â€¢", "•")
                    lines = []
                    for line in cleaned.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        if not line.startswith("•") and not line.startswith("-") and not line.startswith("*"):
                            line = "• " + line
                        elif line.startswith("-") or line.startswith("*"):
                            line = "•" + line[1:]
                        lines.append(line)
                    return "\n".join(lines)
                return str(desc)

            def get_description_bullets(desc):
                if not desc:
                    return []
                if isinstance(desc, list):
                    return [str(d).strip().lstrip("•-* ").strip() for d in desc if str(d).strip()]
                if isinstance(desc, str):
                    cleaned = desc.replace("â€¢", "•")
                    bullets = []
                    for line in cleaned.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        # Strip bullet symbols to return pure text
                        for sym in ["•", "-", "*"]:
                            if line.startswith(sym):
                                line = line[len(sym):].strip()
                        if line:
                            bullets.append(line)
                    return bullets
                return [str(desc)]

            def format_percentage(val):
                if not val:
                    return "Not Mentioned"
                import re
                val_str = str(val).strip()
                if val_str.lower() in ["", "none", "null", "unknown", "na", "n/a", "not mentioned"]:
                    return "Not Mentioned"
                match = re.match(r'^([0-9]+(?:\.[0-9]+)?)\s*(?:cgpa|gpa)?$', val_str, re.IGNORECASE)
                if match:
                    num = float(match.group(1))
                    if num <= 10.0:
                        return f"{match.group(1)}/10"
                cleaned = re.sub(r'\s*(?:cgpa|gpa)\s*', '', val_str, flags=re.IGNORECASE).strip()
                if re.match(r'^[0-9]+(?:\.[0-9]+)?\s*/\s*[0-9]+(?:\.[0-9]+)?$', cleaned):
                    return cleaned.replace(" ", "")
                return val_str

            formatted_jobs = []
            for job in (res.get("experience_details") or []):
                if isinstance(job, dict):
                    formatted_jobs.append({
                        "job_title": job.get("job_title"),
                        "company": job.get("company"),
                        "start_date": job.get("start_date"),
                        "end_date": job.get("end_date"),
                        "description": get_description_bullets(job.get("description"))
                    })

            formatted_projects = []
            for proj in (res.get("projects") or []):
                if isinstance(proj, dict):
                    formatted_projects.append({
                        "project_title": proj.get("project_title"),
                        "description": get_description_bullets(proj.get("description")),
                        "tech_stack": proj.get("tech_stack") or [],
                        "start_date": proj.get("start_date"),
                        "end_date": proj.get("end_date")
                    })
                elif isinstance(proj, str):
                    formatted_projects.append({
                        "project_title": proj,
                        "description": [],
                        "tech_stack": [],
                        "start_date": "",
                        "end_date": ""
                    })

            formatted_education = []
            for edu in (res.get("education_details") or []):
                if isinstance(edu, dict):
                    formatted_education.append({
                        "degree": edu.get("degree"),
                        "institution": edu.get("institution"),
                        "field_of_study": edu.get("field_of_study"),
                        "start_year": edu.get("start_year"),
                        "end_year": edu.get("end_year"),
                        "percentage": format_percentage(edu.get("percentage"))
                    })

            return {
                "id": res.get("id"),
                "application_id": res.get("application_id"),
                "job_id": res.get("job_id"),
                "name": res.get("name"),
                "designation": res.get("designation"),
                "current_location": res.get("current_location"),
                "email": res.get("email"),
                "notice_period": res.get("notice_period"),
                "phone_no": res.get("phone_no"),
                "current_company": res.get("current_company"),
                "personal_details": {
                    "personal_date_of_birth": res.get("personal_date_of_birth"),
                    "personal_gender": res.get("personal_gender"),
                    "personal_nationality": res.get("personal_nationality"),
                    "personal_languages_known": res.get("personal_languages_known") or [],
                    "personal_address": res.get("personal_address")
                },
                "education": formatted_education,
                "experience": {
                    "total_experience": total_exp_str,
                    "relevant_experience": relevant_exp_str,
                    "companies_worked": companies_worked_str,
                    "average_tenure": average_tenure_str,
                    "experience_details": formatted_jobs,
                    "time_line": res.get("time_line") or [],
                    "company_details": res.get("company_details") or [],
                    "list_of_experience": res.get("list_of_experience") or []
                },
                "projects": {
                    "total_projects_count": len(formatted_projects),
                    "project_details": formatted_projects
                },
                "certifications": res.get("certifications") or [],
                "created_at": res.get("created_at"),
                "updated_at": res.get("updated_at"),
                "is_deleted": res.get("is_deleted", False)
            }

        if application_id is not None:
            resume_update = session.exec(
                select(models.ResumeAnalysisUpdate).where(
                    models.ResumeAnalysisUpdate.application_id == application_id
                )
            ).first()
            if resume_update:
                formatted_data = format_resume_update(resume_update)
                return {"success": True, "data": formatted_data}
            else:
                return {"success": False, "message": "No detailed resume analysis update found for this application ID."}
        else:
            resume_updates = session.exec(select(models.ResumeAnalysisUpdate)).all()
            res_list = [format_resume_update(item) for item in resume_updates]
            return {"success": True, "data": res_list}
    except SQLAlchemyError as e:
        print("ERROR:", repr(e))
        raise HTTPException(status_code=500, detail="Database operation failed")
    except Exception as e:
        print("🔥 ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


def add_interview_details(results_db, session):
    updated_results = []

    for obj in results_db:
        # ✅ FIX: object access instead of dict
        application_id = obj.application_id

        if application_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=consts.APPLICATION_ID_NOT_FOUND,
            )

        # convert object → dict
        result = obj.model_dump()

        # -------------------------------
        # Interview session
        # -------------------------------
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

        result["interview_mail_sent"] = True if interview_session else False
        result["interview_status"] = (
            interview_analysis.status if interview_analysis else None
        )
        result["interview_recommendation"] = (
            interview_analysis.recommendation if interview_analysis else None
        )
        result["interview_session_id"] = interview_session.interview_session_id if interview_session else None
        result["questions_status"] = interview_session.questions_status if interview_session else False
        result["move_to_schedule"] = interview_session.move_to_schedule if interview_session else False
        result["move_to_schedule_datetime"] = (
            timezone_utils.format_datetime_for_api(interview_session.move_to_schedule_datetime)
            if (interview_session and interview_session.move_to_schedule_datetime)
            else None
        )
        
        scheduled_by = interview_session.scheduled_by if (interview_session and interview_session.scheduled_by) else None
        result["scheduled_by"] = scheduled_by
        if scheduled_by == "candidate":
            result["scheduled_by_display"] = "Candidate (Self Scheduled)"
        elif scheduled_by == "recruiter":
            result["scheduled_by_display"] = "Recruiter (On Behalf)"
        else:
            result["scheduled_by_display"] = None




        # -------------------------------
        # Candidate decision
        # -------------------------------
        candidate_info = session.exec(
            select(models.CandidateInfo).where(
                models.CandidateInfo.application_id == application_id,
            )
        ).first()
        result["candidate_status"] = candidate_info.status if candidate_info else None
        result["candidate_comment"] = candidate_info.comment if candidate_info else None
        # -------------------------------
        # Job details
        # -------------------------------
        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == application_id
            )
        ).first()

        if job_application:
            job_details = session.exec(
                select(models.CreateJobDetails).where(
                    models.CreateJobDetails.job_id == job_application.job_id
                )
            ).first()

            if job_details:
                result["job_title"] = job_details.job_title
                result["job_id"] = job_details.job_id
            else:
                result["job_title"] = None
                result["job_id"] = None
        else:
            result["job_title"] = None
            result["job_id"] = None

        updated_results.append(result)

    return updated_results


# def add_interview_details(results: List[Dict[str, Any]], session: Session):
#     for result in results:
#         application_id = result["application_id"]

#         if application_id is None:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=consts.APPLICATION_ID_NOT_FOUND,
#             )

#         interview_session = session.exec(
#             select(models.InterviewSessions).where(
#                 models.InterviewSessions.application_id == application_id
#             )
#         ).first()

#         interview_analysis = session.exec(
#             select(models.InterviewAnalysis).where(
#                 models.InterviewAnalysis.application_id == application_id
#             )
#         ).first()

#         result["interview_mail_sent"] = True if interview_session else False
#         result["interview_status"] = (
#             interview_analysis.status if interview_analysis else None
#         )
#         result["interview_recommendation"] = (
#             interview_analysis.recommendation if interview_analysis else None
#         )

#         job_application = session.exec(
#             select(models.JobApplications).where(
#                 models.JobApplications.id == application_id
#             )
#         ).first()

#         job_details = session.exec(
#             select(models.CreateJobDetails).where(
#                 models.CreateJobDetails.job_id == job_application.job_id
#             )
#         ).first()

#         result["job_title"] = job_details.job_title
#         result["job_id"] = job_details.job_id

#     return results


@router.get("/attributes", response_model=List[models.ResumeAttributes])
def fetch_resume_attributes(
    application_id: Optional[int] = None,
    session: Session = Depends(deps.get_session),
):
    try:
        if application_id is not None:
            resume_attribute = session.exec(
                select(models.ResumeAttributes).where(
                    models.ResumeAttributes.application_id == application_id
                )
            ).first()
            if not resume_attribute:
                raise HTTPException(
                    status_code=404,
                    detail=consts.INVALID_APPLICATION_ID(application_id),
                )
            result = resume_attribute.model_dump()
            for key, value in result.items():
                if isinstance(value, datetime):
                    result[key] = timezone_utils.format_datetime_for_api(value)
            return [result]
        else:
            all_resume_attributes = session.exec(select(models.ResumeAttributes)).all()
            if not all_resume_attributes:
                raise HTTPException(
                    status_code=404, detail=consts.NO_RESUME_ATTRIBUTES_FOUND
                )

            results = [obj.model_dump() for obj in all_resume_attributes]
            for result in results:
                for key, value in result.items():
                    if isinstance(value, datetime):
                        result[key] = timezone_utils.format_datetime_for_api(value)
            return results
    except HTTPException:
        raise
    except (SQLAlchemyError, OperationalError):
        raise HTTPException(status_code=500, detail=consts.DATABASE_OPERATION_FAILED)
    except Exception:
        raise HTTPException(status_code=500, detail=consts.INTERNAL_SERVER_ERROR)


@router.post("/analyze/all", response_model=Dict[str, Any])
def analyze_all_resumes(
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    try:
        all_applications = session.exec(select(models.JobApplications)).all()
        already_analyzed = []
        for app in all_applications:
            existing_analysis = session.exec(
                select(models.ResumeAnalysis).where(
                    models.ResumeAnalysis.application_id == app.id,
                    models.ResumeAnalysis.success == True,
                )
            ).first()
            if existing_analysis:
                already_analyzed.append(app.id)
        if len(already_analyzed) == len(all_applications) and len(all_applications) > 0:
            return {"message": consts.ALL_RESUMES_ALREADY_ANALYZED, "success": False}
        batch_analyzer = BatchAnalyzer(background_tasks)
        background_tasks.add_task(batch_analyzer.analyze_all_jobs)
        return {
            "message": "Resume analysis queued successfully. Please verify the results in the Application Tracking System in a minute",
            "success": True,
        }
    except ResourceNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=consts.INTERNAL_SERVER_ERROR)


@router.post("/analyze/job", response_model=Dict[str, Any])
def analyse_resumes_by_job_id(
    data: AnalyseResumesByJobIdRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    try:
        applications_to_check = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.job_id.in_(data.job_ids)
            )
        ).all()
        already_analyzed = []
        for app in applications_to_check:
            existing_analysis = session.exec(
                select(models.ResumeAnalysis).where(
                    models.ResumeAnalysis.application_id == app.id,
                    models.ResumeAnalysis.success == True,
                )
            ).first()
            if existing_analysis:
                already_analyzed.append(app.id)
        if (
            len(already_analyzed) == len(applications_to_check)
            and len(applications_to_check) > 0
        ):
            return {
                "message": consts.ALL_RESUMES_ALREADY_ANALYZED_FOR_JOBS,
                "job_ids": data.job_ids,
                "success": False,
            }
        batch_analyzer = BatchAnalyzer(background_tasks)
        background_tasks.add_task(batch_analyzer.analyze_job_applications, data.job_ids)
        return {
            "message": "Resume analysis queued successfully. Please verify the results in the Application Tracking System in a minute",
            "job_id": data.job_ids,
            "results": [],
            "success": True,
        }
    except ResourceNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=consts.INTERNAL_SERVER_ERROR)


@router.post("/analyze/batch", response_model=Dict[str, Any])
def analyze_resumes_batch(
    data: ResumeBatch,
    background_tasks: BackgroundTasks,
    session: Session = Depends(deps.get_session),
):
    try:
        if not data.resume_batch:
            return {"message": consts.NO_APPLICATIONS_PROVIDED, "results": []}
        applications_to_check = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id.in_(data.resume_batch)
            )
        ).all()
        already_analyzed = []
        pending_analysis = []
        missing_job_details = []
        
        for app in applications_to_check:
            # Check if job details exist
            job_details_exist = session.exec(
                select(models.CreateJobDetails).where(
                    models.CreateJobDetails.job_id == app.job_id
                )
            ).first()
            
            if not job_details_exist:
                error_msg = f"Job ID {app.job_id} related data was not present in the CreateJobDetails"
                from app.services.db_operations import log_resume_activity
                log_resume_activity(
                    session,
                    app.id,
                    "FAILED",
                    error_msg,
                    "BatchAnalyzer",
                )
                missing_job_details.append({
                    "application_id": app.id,
                    "job_id": app.job_id,
                    "error": error_msg
                })
                continue

            existing_analysis = session.exec(
                select(models.ResumeAnalysis).where(
                    models.ResumeAnalysis.application_id == app.id,
                    models.ResumeAnalysis.success == True,
                )
            ).first()
            if existing_analysis:
                already_analyzed.append(app.id)
            else:
                pending_analysis.append(app.id)

        if not pending_analysis:
            if missing_job_details:
                return {
                    "message": f"Resume analysis could not be queued. {missing_job_details[0]['error']}",
                    "success": False,
                    "errors": missing_job_details,
                    "files_not_found": [],
                }
            if already_analyzed:
                return {
                    "message": consts.RESUME_BATCH_ALREADY_ANALYZED,
                    "success": False,
                    "files_not_found": [],
                }
            return {
                "message": consts.NO_APPLICATIONS_PROVIDED,
                "success": False,
                "files_not_found": [],
            }

        batch_analyzer = BatchAnalyzer(background_tasks)
        background_tasks.add_task(
            batch_analyzer.analyze_job_applications_batch,
            pending_analysis,
            data.batch_id,
        )

        response_payload = {
            "message": "Resume analysis queued successfully. Please verify the results in the Application Tracking System in a minute",
            "success": True,
            "files_not_found": [],
        }
        if missing_job_details:
            response_payload["errors"] = missing_job_details
            response_payload["message"] = (
                f"Resume analysis queued for valid applications. However, some applications were skipped: "
                f"{missing_job_details[0]['error']}"
            )
        return response_payload
    except ResourceNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=consts.INTERNAL_SERVER_ERROR)


@router.get("/logs", response_model=List[models.ResumeLogs])
def fetch_resume_logs(
    id: Optional[int] = None,
    application_id: Optional[int] = None,
    page: int = Query(consts.DEFAULT_PAGE, ge=1),
    limit: int = Query(consts.DEFAULT_LIMIT, ge=1),
    session: Session = Depends(deps.get_session),
):
    try:
        if id is not None:
            resume_log = session.exec(
                select(models.ResumeLogs).where(models.ResumeLogs.id == id)
            ).first()
            if not resume_log:
                raise HTTPException(
                    status_code=404, detail=consts.INVALID_RESUME_LOG_ID(id)
                )
            result = resume_log.model_dump()
            for key, value in result.items():
                if isinstance(value, datetime):
                    result[key] = timezone_utils.format_datetime_for_api(value)
            return [result]
        elif application_id is not None:
            resume_log = session.exec(
                select(models.ResumeLogs).where(
                    models.ResumeLogs.application_id == application_id
                )
            ).first()
            if not resume_log:
                raise HTTPException(
                    status_code=404,
                    detail=consts.INVALID_JOB_APPLICATION_ID(application_id),
                )
            result = resume_log.model_dump()
            for key, value in result.items():
                if isinstance(value, datetime):
                    result[key] = timezone_utils.format_datetime_for_api(value)
            return [result]
        else:
            offset = (page - 1) * limit
            resume_logs = session.exec(
                select(models.ResumeLogs).offset(offset).limit(limit)
            ).all()
            results = [obj.model_dump() for obj in resume_logs]
            for result in results:
                for key, value in result.items():
                    if isinstance(value, datetime):
                        result[key] = timezone_utils.format_datetime_for_api(value)
            return results
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail=consts.DATABASE_OPERATION_FAILED)
    except Exception as e:
        raise HTTPException(status_code=500, detail=consts.INTERNAL_SERVER_ERROR)


from sqlalchemy import update
import logging

logger = logging.getLogger(__name__)
from app.services.minio_helper import delete_s3_object


def extract_object_name(url):
    return url.split(f"{consts.INFOSPOKE_S3_BUCKET_NAME}/")[-1]


# from app.utils.delete_entries import soft_delete_job_application


# @router.delete("/job-application/delete")
# def delete_job_application(
#     data: DeleteResumeLogRequest,
#     session: Session = Depends(deps.get_session),
# ):
#     try:
#         success, message = soft_delete_job_application(data.application_id, session)

#         if not success:
#             return {
#                 "delete_success": False,
#                 "message": message,
#             }

#         session.commit()

#         return {
#             "delete_success": True,
#             "message": message,
#         }

#     except Exception as err:
#         session.rollback()
#         logger.error(f"DELETE ERROR: {err}")

#         return {
#             "delete_success": False,
#             "message": consts.JOB_APPLICATION_FOREIGN_DATA_DELETE_FAILED,
#             "error": str(err),
#         }


# from app.utils.delete_entries import delete_candidate_by_id


# @router.delete("/candidate/delete")
# def delete_candidates(
#     candidate_id: List[int] = Body(...),
#     session: Session = Depends(deps.get_session),
# ):
#     try:
#         for cid in candidate_id:
#             success, message = delete_candidate_by_id(cid, session)

#             if not success:
#                 return {"success": False, "message": message}

#         session.commit()

#         return {
#             "success": True,
#             "message": "Candidates deleted successfully",
#         }

#     except Exception as err:
#         session.rollback()
#         logger.error(f"DELETE ERROR: {err}")

#         return {
#             "success": False,
#             "message": "Delete failed",
#             "error": str(err),
#         }


# from app.utils.delete_entries import delete_employee_by_candidate_id


# @router.delete("/employee/delete")
# def delete_employees(
#     candidate_id: List[int] = Body(...),
#     session: Session = Depends(deps.get_session),
# ):
#     try:
#         deleted = []
#         failed = []

#         for cid in candidate_id:

#             success, message = delete_employee_by_candidate_id(cid, session)

#             if success:
#                 deleted.append({"candidate_id": cid, "message": message})
#             else:
#                 failed.append({"candidate_id": cid, "message": message})

#         return {"success": len(failed) == 0, "deleted": deleted, "failed": failed}

#     except Exception as err:
#         logger.error(f"DELETE ERROR: {err}")

#         return {
#             "success": False,
#             "message": "Employee delete failed",
#             "error": str(err),
#         }


# @router.delete("/job-applications/delete")
# def delete_job_applications(
#     data: DeleteResumeLogsRequest,
#     session: Session = Depends(deps.get_session),
# ):
#     try:
#         print(f"{data.application_ids = }")
#         for application_id in data.application_ids:
#             # --- Delete ResumeLogs ---
#             session.exec(
#                 delete(models.ResumeLogs).where(
#                     models.ResumeLogs.application_id == application_id
#                 )
#             )

#             # --- Delete ResumeAttributes ---
#             session.exec(
#                 delete(models.ResumeAttributes).where(
#                     models.ResumeAttributes.application_id == application_id
#                 )
#             )

#             # --- Delete ResumeAnalysis ---
#             session.exec(
#                 delete(models.ResumeAnalysis).where(
#                     models.ResumeAnalysis.application_id == application_id
#                 )
#             )

#             # --- Fetch interview_session_id ---
#             interview_session = session.exec(
#                 select(models.InterviewSessions).where(
#                     models.InterviewSessions.application_id == application_id
#                 )
#             ).first()
#             interview_session_id = (
#                 interview_session.interview_session_id if interview_session else None
#             )

#             # --- Fetch interview_analysis_id ---
#             interview_analysis = session.exec(
#                 select(models.InterviewAnalysis).where(
#                     models.InterviewAnalysis.application_id == application_id
#                 )
#             ).first()
#             interview_analysis_id = (
#                 interview_analysis.id if interview_analysis else None
#             )

#             if interview_analysis_id is not None:
#                 # --- Delete QNA_Analysis ---
#                 session.exec(
#                     delete(models.QNA_Analysis).where(
#                         models.QNA_Analysis.interview_analysis_id
#                         == interview_analysis_id
#                     )
#                 )

#                 # --- Delete ProctoringLogs ---
#                 session.exec(
#                     delete(models.ProctoringLogs).where(
#                         models.ProctoringLogs.interview_analysis_id
#                         == interview_analysis_id
#                     )
#                 )

#                 # --- Delete InterviewAnalysis ---
#                 session.exec(
#                     delete(models.InterviewAnalysis).where(
#                         models.InterviewAnalysis.id == interview_analysis_id
#                     )
#                 )

#             if interview_session_id is not None:
#                 # --- Delete InterviewSessions ---
#                 session.exec(
#                     delete(models.InterviewSessions).where(
#                         models.InterviewSessions.interview_session_id
#                         == interview_session_id
#                     )
#                 )

#             session.commit()
#         return {
#             "delete_success": True,
#             "message": consts.JOB_APPLICATION_FOREIGN_DATA_DELETED,
#         }
#     except Exception as err:
#         return {
#             "delete_success": False,
#             "message": consts.JOB_APPLICATION_FOREIGN_DATA_DELETE_FAILED,
#             "error": consts.INTERNAL_SERVER_ERROR,
#         }


def calculate_stats(all_results, results, total_candidates, page, total_pages):
    analyzed_resumes = [r for r in all_results if r.success]
    total_analyzed = len(analyzed_resumes)

    if total_analyzed > 0:
        avg_score = sum(r.final_score for r in analyzed_resumes) / total_analyzed
        avg_time = sum(r.processing_time for r in analyzed_resumes) / total_analyzed
    else:
        avg_score = 0.0
        avg_time = 0.0

    score_dist = {
        "excellent": len([r for r in analyzed_resumes if r.final_score >= 80]),
        "good": len([r for r in analyzed_resumes if 70 <= r.final_score < 80]),
        "average": len([r for r in analyzed_resumes if 50 <= r.final_score < 70]),
        "below_average": len([r for r in analyzed_resumes if r.final_score < 50]),
    }

    hiring_recs = {
        "hire": len(
            [r for r in analyzed_resumes if r.recommendation_decision.upper() == "HIRE"]
        ),
        "consider": len(
            [
                r
                for r in analyzed_resumes
                if r.recommendation_decision.upper() == "CONSIDER"
            ]
        ),
        "reject": len(
            [
                r
                for r in analyzed_resumes
                if r.recommendation_decision.upper() == "REJECT"
            ]
        ),
    }

    stats = {
        "total_resumes": total_candidates,
        "total_analyzed_resumes": total_analyzed,
        "average_score": round(avg_score, 2),
        "average_processing_time": round(avg_time, 2),
        "score_distribution": score_dist,
        "hiring_recommendations": hiring_recs,
        "page": page,
        "total_pages": total_pages,
    }

    return {"resume_analysis": results, "statistics": stats}