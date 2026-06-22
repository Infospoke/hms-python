import json
import logging
from typing import Optional, List, Dict
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import or_, and_
from datetime import datetime
from app.utils.timezone_utils import get_ist_now
import app.models as models
from app.core.exceptions import (
    DatabaseQueryException,
    DatabaseIntegrityException,
    ResourceNotFoundException,
)
import re

logger = logging.getLogger(__name__)


def extract_relative_path(full_path):
    if not full_path:
        return ""
    match = re.search("[/\\\\]static[/\\\\]", full_path, re.IGNORECASE)
    if match:
        start_idx = match.start()
        relative = full_path[start_idx:]
        if not relative.startswith("\\"):
            relative = "\\" + relative.replace("/", "\\")
        return relative
    return full_path


def get_job_application_by_id(
    session: Session, application_id: int
) -> Optional[models.JobApplications]:
    try:
        logger.debug(f"Searching for JobApplications with ID: {application_id}")
        statement = select(models.JobApplications).where(
            models.JobApplications.id == application_id
        )
        job_application = session.exec(statement).first()
        if job_application:
            logger.debug(f"JobApplications found for ID {application_id}")
            return job_application
        else:
            logger.debug(f"No JobApplications found for ID {application_id}")
            return None
    except SQLAlchemyError as e:
        logger.error(f"Database query error: {str(e)}")
        raise DatabaseQueryException(str(e), "get_job_application_by_id")
    except Exception as e:
        logger.error(f"Unexpected error in get_job_application_by_id: {str(e)}")
        raise DatabaseQueryException(str(e), "get_job_application_by_id")


def create_or_update_json_analysis_db(
    session: Session, application_id: int, result: Dict, analysis_success: bool
) -> Optional[models.ResumeAttributes]:
    resume_attributes = create_or_update_resume_attributes_db(
        session, application_id, result, analysis_success
    )
    resume_analysis = create_or_update_resume_analysis_db(
        session, application_id, result, analysis_success
    )
    if analysis_success:
        try:
            create_or_update_resume_analysis_update_db(
                session, application_id, result
            )
        except Exception as e:
            logger.error(f"Failed to save detailed resume analysis update to DB: {e}")
    return resume_attributes


def create_or_update_resume_attributes_db(
    session: Session, application_id: int, result: Dict, analysis_success: bool
) -> Optional[models.ResumeAttributes]:
    try:
        job_application = get_job_application_by_id(session, application_id)
        if not job_application:
            logger.error(
                f"Could not find JobApplications record with ID {application_id}"
            )
            raise ResourceNotFoundException("JobApplications", f"id={application_id}")
        statement = select(models.ResumeAttributes).where(
            models.ResumeAttributes.application_id == job_application.id
        )
        resume_attribute = session.exec(statement).first()
        analysis_json_str = json.dumps(result)
        if resume_attribute:
            resume_attribute.analysis_json = analysis_json_str
            resume_attribute.analysis_success = analysis_success
            resume_attribute.updated_date = get_ist_now()
            logger.info(f"Resume analysis updated for application ID {application_id}")
        else:
            resume_attribute = models.ResumeAttributes(
                application_id=job_application.id,
                analysis_json=analysis_json_str,
                analysis_success=analysis_success,
                custom_attributes="{}",
            )
            logger.info(f"Resume analysis created for application ID {application_id}")
        session.add(resume_attribute)
        session.commit()
        session.refresh(resume_attribute)
        return resume_attribute
    except (ResourceNotFoundException, DatabaseQueryException):
        raise
    except IntegrityError as e:
        session.rollback()
        logger.error(f"Database integrity error: {str(e)}")
        raise DatabaseIntegrityException(str(e))
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error: {str(e)}")
        raise DatabaseQueryException(str(e), "create_or_update_resume_attributes_db")
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating/updating resume analysis: {str(e)}")
        raise DatabaseQueryException(str(e), "create_or_update_resume_attributes_db")


def create_or_update_resume_analysis_db(
    session: Session, application_id: int, result: Dict, analysis_success: bool
) -> Optional[models.ResumeAnalysis]:
    try:
        job_application = get_job_application_by_id(session, application_id)
        if not job_application:
            logger.error(
                f"Could not find JobApplications record with ID {application_id}"
            )
            raise ResourceNotFoundException("JobApplications", f"id={application_id}")
        statement = select(models.ResumeAnalysis).where(
            models.ResumeAnalysis.application_id == job_application.id
        )
        resume_analysis = session.exec(statement).first()
        if resume_analysis:
            job_id = (
            session.exec(
                select(models.JobApplications).where(
                    models.JobApplications.id == application_id
                )
            )
            .first()
            .job_id
            )
            resume_analysis.success = analysis_success
            resume_analysis.job_id = job_id
            resume_analysis.updated_at = get_ist_now()
            logger.info(f"Resume analysis updated for application ID {application_id}")
        else:
            resume_analysis = models.ResumeAnalysis(
                application_id=job_application.id,
                job_id=job_application.job_id,
                candidate_name=result.get("candidate_name", "No Name Found"),
                email=result.get("email", "No Email Found"),
                contact_number=result.get("contact_number"),
                final_score=result.get("scores", dict()).get("final_score", 0.0),
                skills_match=result.get("scores", dict()).get("skills_match", 0.0),
                experience_score=result.get("scores", dict()).get(
                    "experience_score", 0.0
                ),
                education_score=result.get("scores", dict()).get(
                    "education_score", 0.0
                ),
                keywords_match=result.get("scores", dict()).get("keywords_match", 0.0),
                overall_fit=result.get("scores", dict()).get("overall_fit", 0.0),
                growth_potential=result.get("scores", dict()).get(
                    "growth_potential", 0.0
                ),
                recommendation_decision=result.get("recommendation", dict()).get(
                    "decision", ""
                ),
                recommendation_reason=result.get("recommendation", dict()).get(
                    "reason", ""
                ),
                recommendation_confidence=result.get("recommendation", dict()).get(
                    "confidence", ""
                ),
                skill_match_percentage=result.get("skills_analysis", dict()).get(
                    "skill_match_percentage", 0.0
                ),
                tb_matching_skills=result.get("skills_analysis", dict()).get(
                    "tb_matching_skills", []
                ),
                tb_missing_skills=result.get("skills_analysis", dict()).get(
                    "tb_missing_skills", []
                ),
                tb_matching_experience=result.get("experience_analysis", dict()).get(
                    "tb_matching_experience", []
                ),
                tb_experience_gaps=result.get("experience_analysis", dict()).get(
                    "tb_experience_gaps", []
                ),
                experience_level=result.get("experience_analysis", dict()).get(
                    "experience_level", ""
                ),
                tb_education_highlights=result.get("education_analysis", dict()).get(
                    "tb_education_highlights", []
                ),
                education_level=result.get("education_analysis", dict()).get(
                    "education_level", ""
                ),
                is_fresher=result.get("job_analysis", dict()).get("fresher", None),
                first_job_start_year=result.get("job_analysis", dict()).get(
                    "first_job_start_year", 0
                ),
                last_job_end_year=result.get("job_analysis", dict()).get(
                    "last_job_end_year", 0
                ),
                total_jobs_count=result.get("job_analysis", dict()).get(
                    "total_jobs_count", 0
                ),
                average_job_change=result.get("job_analysis", dict()).get(
                    "average_job_change", None
                ),
                tb_strengths=result.get("assessment", dict()).get("tb_strengths", []),
                tb_weaknesses=result.get("assessment", dict()).get("tb_weaknesses", []),
                tb_red_flags=result.get("assessment", dict()).get("tb_red_flags", []),
                tb_cultural_fit_indicators=result.get("assessment", dict()).get(
                    "cultural_fit_indications"
                ),
                salary_expectation_alignment=result.get("hiring_insights", dict()).get(
                    "salary_expectation_alignment", ""
                ),
                onboarding_priority=result.get("hiring_insights", dict()).get(
                    "onboarding_priority", ""
                ),
                tb_interview_focus_areas=result.get("hiring_insights", dict()).get(
                    "interview_foucs_areas", []
                ),
                processing_time=result.get("metadata", dict()).get(
                    "processing_time", 0.0
                ),
                processed_at=result.get("metadata", dict()).get("processed_at", None),
                file_path=extract_relative_path(
                    result.get("metadata", dict()).get("file_path", "")
                ),
                file_size=result.get("metadata", dict()).get("file_size", 0),
                word_count=result.get("metadata", dict()).get("word_count", 0),
                success=result.get("metadata", dict()).get("success", False),
                error_message=result.get("error", None),
            )
            logger.info(f"Resume analysis created for application ID {application_id}")
        # Always derive status from the final score
        final_score = resume_analysis.final_score or 0.0
        resume_analysis.status = "Shortlisted" if final_score > 50 else "Not Shortlisted"
        session.add(resume_analysis)
        session.commit()
        session.refresh(resume_analysis)
        return resume_analysis
    except (ResourceNotFoundException, DatabaseQueryException):
        raise
    except IntegrityError as e:
        session.rollback()
        logger.error(f"Database integrity error: {str(e)}")
        raise DatabaseIntegrityException(str(e))
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error: {str(e)}")
        raise DatabaseQueryException(str(e), "create_or_update_resume_analysis_db")
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error creating/updating resume analysis: {str(e)}")
        raise DatabaseQueryException(str(e), "create_or_update_resume_analysis_db")


def update_analysis_in_db(session: Session, application_id: int):
    try:
        resume_analysis = session.exec(
            select(models.ResumeAnalysis).where(
                models.ResumeAnalysis.application_id == application_id
            )
        ).first()
        
        job_id = (
            session.exec(
                select(models.JobApplications).where(
                    models.JobApplications.id == application_id
                )
            )
            .first()
            .job_id
        )
        
        if resume_analysis:
            resume_analysis.success = True
            resume_analysis.job_id = job_id
            session.add(resume_analysis)
            session.commit()
            logger.info(f"Analysis status updated for application ID {application_id}")
        else:
            logger.warning(f"No ResumeAnalysis record found for ID {application_id}")
        resume_attributes = session.exec(
            select(models.ResumeAttributes).where(
                models.ResumeAttributes.application_id == application_id
            )
        ).first()
        if resume_attributes:
            resume_attributes.analysis_success = True
            session.add(resume_attributes)
            session.commit()
            logger.info(f"Analysis status updated for application ID {application_id}")
        else:
            logger.warning(f"No ResumeAttributes record found for ID {application_id}")
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error updating analysis status: {str(e)}")
        raise DatabaseQueryException(str(e), "update_analysis_in_db")
    except Exception as e:
        session.rollback()
        logger.error(
            f"Error updating analysis status for ID {application_id}: {str(e)}"
        )
        raise DatabaseQueryException(str(e), "update_analysis_in_db")


def fetch_analysis_from_db(session: Session, application_id: int) -> Dict:
    try:
        job_application = get_job_application_by_id(session, application_id)
        if not job_application:
            logger.warning(f"No JobApplications found for ID {application_id}")
            return {}
        statement = select(models.ResumeAttributes).where(
            models.ResumeAttributes.application_id == job_application.id
        )
        resume_attribute = session.exec(statement).first()
        if resume_attribute and resume_attribute.analysis_json:
            return json.loads(resume_attribute.analysis_json)
        return {}
    except SQLAlchemyError as e:
        logger.error(f"Database query error: {str(e)}")
        raise DatabaseQueryException(str(e), "fetch_analysis_from_db")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error fetching analysis: {str(e)}")
        raise DatabaseQueryException(str(e), "fetch_analysis_from_db")


def get_results_by_job_id(session: Session, job_id: int) -> List[Dict]:
    try:
        results = []
        statement = (
            select(models.ResumeAttributes)
            .join(models.JobApplications)
            .where(models.ResumeAttributes.analysis_success == True)
        )
        resume_attributes = session.exec(statement).all()
        for resume_attribute in resume_attributes:
            if resume_attribute.analysis_json:
                result = json.loads(resume_attribute.analysis_json)
                results.append(result)
        logger.info(f"Retrieved {len(results)} analysis results")
        return results
    except SQLAlchemyError as e:
        logger.error(f"Database query error: {str(e)}")
        raise DatabaseQueryException(str(e), "get_results_by_job_id")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching results: {str(e)}")
        raise DatabaseQueryException(str(e), "get_results_by_job_id")


def get_unanalysed_data(
    session: Session, job_id: Optional[int] = None
) -> Optional[List[Dict]]:
    try:
        if job_id is None:
            statement = (
                select(models.JobApplications)
                .outerjoin(
                    models.ResumeAnalysis,
                    models.ResumeAnalysis.application_id == models.JobApplications.id,
                )
                .where(
                    or_(
                        models.ResumeAnalysis.id == None,
                        models.ResumeAnalysis.success == False,
                    )
                )
            )
        else:
            statement = (
                select(models.JobApplications)
                .outerjoin(
                    models.ResumeAnalysis,
                    models.ResumeAnalysis.application_id == models.JobApplications.id,
                )
                .where(
                    and_(
                        models.JobApplications.job_id == job_id,
                        or_(
                            models.ResumeAnalysis.id == None,
                            models.ResumeAnalysis.success == False,
                        ),
                    )
                )
            )
        unanalysed_data_queryset = session.exec(statement).all()
        unanalysed_data = []
        for job_application in unanalysed_data_queryset:
            unanalysed_data.append(
                {
                    "id": job_application.id,
                    "first_name": job_application.first_name,
                    "last_name": job_application.last_name,
                    "email": job_application.email,
                    "ph_no": job_application.ph_no,
                    "resume": job_application.resume,
                    "job_id": job_application.job_id,
                }
            )
        logger.info(
            f"Retrieved {len(unanalysed_data)} unanalyzed applications for job_id {job_id}"
        )
        return unanalysed_data if unanalysed_data else None
    except SQLAlchemyError as e:
        logger.error(f"Database query error: {str(e)}")
        raise DatabaseQueryException(str(e), "get_unanalysed_data")
    except Exception as e:
        logger.error(f"Unexpected error fetching unanalyzed data: {str(e)}")
        raise DatabaseQueryException(str(e), "get_unanalysed_data")


def log_resume_activity(
    session: Session,
    application_id: int,
    status: str,
    message: str,
    component: str = None,
) -> None:
    try:
        log_entry = models.ResumeLogs(
            application_id=application_id,
            log_message=message,
            status=status,
            component=component,
        )
        session.add(log_entry)
        session.commit()
    except Exception as e:
        logger.error(f"Failed to create resume log for app {application_id}: {e}")


def create_or_update_resume_analysis_update_db(
    session: Session, application_id: int, result: Dict
) -> Optional[models.ResumeAnalysisUpdate]:
    try:
        job_application = get_job_application_by_id(session, application_id)
        if not job_application:
            logger.error(
                f"Could not find JobApplications record with ID {application_id}"
            )
            return None
        
        statement = select(models.ResumeAnalysisUpdate).where(
            models.ResumeAnalysisUpdate.application_id == job_application.id
        )
        resume_analysis_update = session.exec(statement).first()
        
        # Extract details with safe fallback defaults from nested analysis dictionary
        analysis = result.get("analysis", {})
        
        def clean_val(val):
            if val is None:
                return "Not Mentioned"
            if isinstance(val, str):
                s = val.strip()
                if not s or s.lower() in ["", "none", "null", "unknown", "na", "n/a", "not found", "no name found", "no email found"]:
                    return "Not Mentioned"
                return s
            return str(val)
        
        name = clean_val(result.get("name") or analysis.get("name") or result.get("candidate_name") or analysis.get("candidate_name"))
        designation = clean_val(result.get("designation") or analysis.get("designation") or result.get("current_role") or analysis.get("current_role"))
        current_location = clean_val(result.get("current_location") or analysis.get("current_location") or result.get("location") or analysis.get("location"))
        total_experience = clean_val(result.get("total_experience") or analysis.get("total_experience") or result.get("relevant_experience_years") or analysis.get("relevant_experience_years"))
        email = clean_val(result.get("email") or analysis.get("email"))
        notice_period = clean_val(result.get("notice_period") or analysis.get("notice_period"))
        phone_no = clean_val(result.get("phone_no") or analysis.get("phone_no") or result.get("contact_number") or analysis.get("contact_number") or result.get("phone_fields") or result.get("phone") or analysis.get("phone"))
        current_company = clean_val(result.get("current_company") or analysis.get("current_company"))
        
        personal_date_of_birth = clean_val(result.get("personal_date_of_birth") or analysis.get("personal_date_of_birth"))
        personal_gender = clean_val(result.get("personal_gender") or analysis.get("personal_gender"))
        personal_nationality = clean_val(result.get("personal_nationality") or analysis.get("personal_nationality"))
        personal_languages_known = result.get("personal_languages_known") or analysis.get("personal_languages_known") or []
        personal_address = clean_val(result.get("personal_address") or analysis.get("personal_address"))
        
        education_details = result.get("education_details") or analysis.get("education_details") or []
        experience_details = result.get("experience_details") or analysis.get("experience_details") or []
        time_line = result.get("time_line") or analysis.get("time_line") or []
        company_details = result.get("company_details") or analysis.get("company_details") or []
        list_of_experience = result.get("list_of_experience") or analysis.get("list_of_experience") or []
        projects = result.get("projects") or analysis.get("projects") or []
        certifications = result.get("certifications") or analysis.get("certifications") or []
        
        # Calculate total projects count
        total_projects_count = result.get("total_projects_count") or analysis.get("total_projects_count")
        if total_projects_count is None:
            total_projects_count = len(projects)
            
        if resume_analysis_update:
            resume_analysis_update.job_id = job_application.job_id
            resume_analysis_update.name = name
            resume_analysis_update.designation = designation
            resume_analysis_update.current_location = current_location
            resume_analysis_update.total_experience = total_experience
            resume_analysis_update.email = email
            resume_analysis_update.notice_period = notice_period
            resume_analysis_update.phone_no = phone_no
            resume_analysis_update.current_company = current_company
            resume_analysis_update.personal_date_of_birth = personal_date_of_birth
            resume_analysis_update.personal_gender = personal_gender
            resume_analysis_update.personal_nationality = personal_nationality
            resume_analysis_update.personal_languages_known = personal_languages_known
            resume_analysis_update.personal_address = personal_address
            resume_analysis_update.education_details = education_details
            resume_analysis_update.experience_details = experience_details
            resume_analysis_update.time_line = time_line
            resume_analysis_update.company_details = company_details
            resume_analysis_update.list_of_experience = list_of_experience
            resume_analysis_update.projects = projects
            resume_analysis_update.certifications = certifications
            resume_analysis_update.total_projects_count = total_projects_count
            resume_analysis_update.updated_at = get_ist_now()
            logger.info(f"ResumeAnalysisUpdate updated for application ID {application_id}")
        else:
            resume_analysis_update = models.ResumeAnalysisUpdate(
                application_id=job_application.id,
                job_id=job_application.job_id,
                name=name,
                designation=designation,
                current_location=current_location,
                total_experience=total_experience,
                email=email,
                notice_period=notice_period,
                phone_no=phone_no,
                current_company=current_company,
                personal_date_of_birth=personal_date_of_birth,
                personal_gender=personal_gender,
                personal_nationality=personal_nationality,
                personal_languages_known=personal_languages_known,
                personal_address=personal_address,
                education_details=education_details,
                experience_details=experience_details,
                time_line=time_line,
                company_details=company_details,
                list_of_experience=list_of_experience,
                projects=projects,
                certifications=certifications,
                total_projects_count=total_projects_count
            )
            logger.info(f"ResumeAnalysisUpdate created for application ID {application_id}")
            
        session.add(resume_analysis_update)
        session.commit()
        session.refresh(resume_analysis_update)
        return resume_analysis_update
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error in create_or_update_resume_analysis_update_db: {str(e)}")
        raise DatabaseQueryException(str(e), "create_or_update_resume_analysis_update_db")
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error in create_or_update_resume_analysis_update_db: {str(e)}")
        raise DatabaseQueryException(str(e), "create_or_update_resume_analysis_update_db")
