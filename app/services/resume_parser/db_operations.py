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
                matching_skills=result.get("skills_analysis", dict()).get(
                    "matching_skills", []
                ),
                missing_skills=result.get("skills_analysis", dict()).get(
                    "missing_skills", []
                ),
                matching_experience=result.get("experience_analysis", dict()).get(
                    "matching_experience", []
                ),
                experience_gaps=result.get("experience_analysis", dict()).get(
                    "experience_gaps", []
                ),
                experience_level=result.get("experience_analysis", dict()).get(
                    "experience_level", ""
                ),
                education_highlights=result.get("education_analysis", dict()).get(
                    "education_highlights", []
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
                strengths=result.get("assessment", dict()).get("strengths", []),
                weaknesses=result.get("assessment", dict()).get("weaknesses", []),
                red_flags=result.get("assessment", dict()).get("red_flags", []),
                cultural_fit_indicators=result.get("assessment", dict()).get(
                    "cultural_fit_indications"
                ),
                salary_expectation_alignment=result.get("hiring_insights", dict()).get(
                    "salary_expectation_alignment", ""
                ),
                onboarding_priority=result.get("hiring_insights", dict()).get(
                    "onboarding_priority", ""
                ),
                interview_focus_areas=result.get("hiring_insights", dict()).get(
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
