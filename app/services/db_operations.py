import json
import logging
from typing import Optional, List, Dict
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import or_, and_
from datetime import datetime
import app.models as models
from app.core.exceptions import (
    DatabaseQueryException,
    DatabaseIntegrityException,
    ResourceNotFoundException,
)
import re
from app.utils import timezone_utils

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
            resume_attribute.updated_date = timezone_utils.get_ist_now()
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

        scores = result.get("scores", {})
        recommendation = result.get("recommendation", {})
        skills_analysis = result.get("skills_analysis", {})
        experience_analysis = result.get("experience_analysis", {})
        education_analysis = result.get("education_analysis", {})
        job_analysis = result.get("job_analysis", {})
        assessment = result.get("assessment", {})
        hiring_insights = result.get("hiring_insights", {})
        metadata = result.get("metadata", {})

        mapped_values = {
            "candidate_name": result.get("candidate_name", "No Name Found"),
            "email": result.get("email", "No Email Found"),
            "contact_number": result.get("contact_number"),
            "final_score": scores.get("final_score", 0.0),
            "skills_match": scores.get("skills_match", 0.0),
            "experience_score": scores.get("experience_score", 0.0),
            "education_score": scores.get("education_score", 0.0),
            "keywords_match": scores.get("keywords_match", 0.0),
            "overall_fit": scores.get("overall_fit", 0.0),
            "growth_potential": scores.get("growth_potential", 0.0),
            "recommendation_decision": recommendation.get("decision", ""),
            "recommendation_reason": recommendation.get("reason", ""),
            "recommendation_confidence": recommendation.get("confidence", ""),
            "skill_match_percentage": skills_analysis.get(
                "skill_match_percentage", 0.0
            ),
            "matching_skills": skills_analysis.get("matching_skills", []),
            "missing_skills": skills_analysis.get("missing_skills", []),
            "matching_experience": experience_analysis.get("matching_experience", []),
            "experience_gaps": experience_analysis.get("experience_gaps", []),
            "experience_level": experience_analysis.get("experience_level", ""),
            "education_highlights": education_analysis.get("education_highlights", []),
            "matching_education": education_analysis.get("matching_education", []),
            "missing_education": education_analysis.get("missing_education", []),
            "education_level": education_analysis.get("education_level", ""),
            "is_fresher": job_analysis.get("fresher", None),
            "first_job_start_year": job_analysis.get("first_job_start_year", 0),
            "last_job_end_year": job_analysis.get("last_job_end_year", 0),
            "total_jobs_count": job_analysis.get("total_jobs_count", 0),
            "average_job_change": job_analysis.get("average_job_change", None),
            "strengths": assessment.get("strengths", []),
            "weaknesses": assessment.get("weaknesses", []),
            "red_flags": assessment.get("red_flags", []),
            "cultural_fit_indicators": assessment.get("cultural_fit_indicators", []),
            "salary_expectation_alignment": hiring_insights.get(
                "salary_expectation_alignment", ""
            ),
            "onboarding_priority": hiring_insights.get("onboarding_priority", ""),
            "interview_focus_areas": hiring_insights.get("interview_focus_areas", []),
            "processing_time": metadata.get("processing_time", 0.0),
            "processed_at": metadata.get("processed_at", None),
            "file_path": extract_relative_path(metadata.get("file_path", "")),
            "file_size": metadata.get("file_size", 0),
            "word_count": metadata.get("word_count", 0),
            "success": metadata.get("success", False),
            "error_message": result.get("error", None),
        }

        if resume_analysis:
            for key, value in mapped_values.items():
                setattr(resume_analysis, key, value)
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
            resume_analysis.updated_at = timezone_utils.get_ist_now()
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
                matching_education=result.get("education_analysis", dict()).get(
                    "matching_education", []
                ),
                missing_education=result.get("education_analysis", dict()).get(
                    "missing_education", []
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
        resume_analysis.status = "Shortlisted" if final_score >= 50 else "Not Shortlisted"

        # Update JobApplications stage and rejection status
        job_application.current_stage = resume_analysis.status
        job_application.stage_entry_date = timezone_utils.get_ist_now()
        if final_score < 50:
            job_application.rejected = True
        
        session.add(job_application)

        candidate_name = get_candidate_name(session, job_application.id)

        activity_feed = models.ActivityFeed(
            timestamp=timezone_utils.get_ist_now(),
            activity=f"Resume screening completed for {candidate_name}",
        )

        session.add(resume_analysis)
        session.add(activity_feed)
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


def create_pending_answers(
    session: Session,
    interview_session_id: str,
    audio_paths: Dict[str, str],
):
    try:
        interview_analysis = session.exec(
            select(models.InterviewAnalysis)
            .join(
                models.InterviewSessions,
                models.InterviewAnalysis.interview_session_id
                == models.InterviewSessions.interview_session_id,
            )
            .where(
                models.InterviewSessions.interview_session_id == interview_session_id
            )
        ).first()

        if not interview_analysis:
            return {"success": False, "error": "Interview analysis not found"}

        for question_index, audio_path in audio_paths.items():
            try:
                idx = int(question_index) - 1
                question_db_id = None
                if 0 <= idx < len(interview_analysis.questions):
                    question_obj = interview_analysis.questions[idx]
                    if isinstance(question_obj, dict):
                        question_text = question_obj.get("question", "")
                        question_db_id = question_obj.get("question_id")
                    else:
                        question_text = str(question_obj)
                else:
                    question_text = "Unknown Question"
            except:
                question_text = "Unknown Question"
                question_db_id = None

            qna_analysis = models.QNA_Analysis(
                application_id=interview_analysis.application_id,
                interview_analysis_id=interview_analysis.id,
                question_id=question_db_id,
                question_text=question_text,
                answer_text=f"AUDIO_PENDING:{audio_path}",
                ai_analysis=None,
            )
            logger.info(f"Created pending QNA entry: {qna_analysis.answer_text}")
            session.add(qna_analysis)

        session.commit()
        logger.info(f"Pending answers created for session {interview_session_id}")
        return {"success": True}
    except Exception as err:
        logger.error(f"Error creating pending answers: {err}")
        return {"success": False, "error": "An internal server error occurred."}


def save_answers(
    session: Session,
    interview_session_id: str,
    transcriptions: Dict[str, str],
    confidence_reports: Optional[Dict[str, Dict]] = None,
):
    try:
        interview_analysis = session.exec(
            select(models.InterviewAnalysis)
            .join(
                models.InterviewSessions,
                models.InterviewAnalysis.interview_session_id
                == models.InterviewSessions.interview_session_id,
            )
            .where(
                models.InterviewSessions.interview_session_id == interview_session_id
            )
        ).first()
        for question_index, answer in transcriptions.items():
            question_obj = interview_analysis.questions[int(question_index) - 1]
            question_text = (
                question_obj
                if isinstance(question_obj, str)
                else question_obj.get("question", "")
            )
            qna_analysis = models.QNA_Analysis(
                interview_analysis_id=interview_analysis.id,
                question_text=question_text,
                answer_text=answer,
                ai_analysis=(
                    confidence_reports.get(question_index)
                    if confidence_reports
                    else None
                ),
            )
            session.add(qna_analysis)
        session.commit()
        return {"success": True}
    except Exception as err:
        logger.error(f"Error saving answers: {err}")
        return {"success": False, "error": "An internal server error occurred."}


def get_and_claim_pending_qna_response(session: Session):
    try:
        from sqlmodel import select
        from sqlalchemy import cast, String
        from app.core import config as consts

        statement = (
            select(models.QNA_Analysis)
            .where(
                or_(
                    models.QNA_Analysis.ai_analysis == None,
                    cast(models.QNA_Analysis.ai_analysis, String) == "{}",
                    models.QNA_Analysis.ai_analysis.op("->>")("status") == None,
                    ~models.QNA_Analysis.ai_analysis.op("->>")("status").in_(
                        ["processing", "completed", "error"]
                    ),
                )
            )
            .where(
                or_(
                    models.QNA_Analysis.answer_text == None,
                    models.QNA_Analysis.answer_text == "",
                    models.QNA_Analysis.answer_text.like("AUDIO_PENDING:%"),
                )
            )
            .order_by(models.QNA_Analysis.created_at)
        )

        if consts.DATABASE_URL and "sqlite" not in consts.DATABASE_URL.lower():
            statement = statement.with_for_update(skip_locked=True)

        record = session.exec(statement).first()

        if record:
            logger.info(
                f"Worker atomically claiming QNA ID: {record.id}  answer: {str(record.answer_text)[:50]!r}"
            )
            if record.ai_analysis is None:
                record.ai_analysis = {"status": "processing"}
            else:
                new_analysis = dict(record.ai_analysis)
                new_analysis["status"] = "processing"
                record.ai_analysis = new_analysis

            session.add(record)
            session.commit()
            session.refresh(record)
            return record

        return None
    except Exception as e:
        logger.error(f"Error claiming pending QNA response: {str(e)}")
        session.rollback()
        return None


def get_pending_qna_count(session: Session, interview_analysis_id: int) -> int:
    try:
        from sqlmodel import select

        statement = select(models.QNA_Analysis).where(
            models.QNA_Analysis.interview_analysis_id == interview_analysis_id
        )
        records = session.exec(statement).all()

        pending_count = 0
        for record in records:
            if not record.ai_analysis:
                pending_count += 1
            else:
                data = record.ai_analysis
                if isinstance(data, str):
                    try:
                        import json

                        data = json.loads(data)
                    except:
                        data = {}

                if isinstance(data, dict):
                    status = data.get("status")
                    if status not in ["completed", "error"] and "overall" not in data:
                        pending_count += 1
                else:
                    pending_count += 1

        return pending_count
    except Exception as e:
        logger.error(f"Error counting pending QNA responses: {str(e)}")
        return 0


def get_interview_context(
    session: Session, interview_analysis_id: int
) -> Optional[dict]:
    try:
        from sqlmodel import select
        from pathlib import Path
        from app.services.resume_parser.s3_resume_parser import S3ResumeParser
        from app.core import config as consts

        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                models.InterviewAnalysis.id == interview_analysis_id
            )
        ).first()
        if not interview_analysis:
            logger.error(f"Interview analysis {interview_analysis_id} not found")
            return None
        job_application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == interview_analysis.application_id
            )
        ).first()
        if not job_application:
            logger.error(
                f"Job application {interview_analysis.application_id} not found"
            )
            return None
        create_job_details = session.exec(
            select(models.CreateJobDetails).where(
                models.CreateJobDetails.job_id == job_application.job_id
            )
        ).first()
        resume_analysis = session.exec(
            select(models.ResumeAnalysis).where(
                models.ResumeAnalysis.application_id
                == interview_analysis.application_id
            )
        ).first()
        if not resume_analysis:
            logger.warning(
                f"Resume analysis not found for application {interview_analysis.application_id}"
            )
        resume_text = ""
        if resume_analysis:
            try:
                resume_parser = S3ResumeParser()
                resume_text = resume_parser.extract_text(resume_analysis.file_path)
                resume_text = resume_text[:1000] if resume_text else ""
            except Exception as e:
                logger.warning(f"Could not extract resume text: {e}")
                resume_text = ""
        from app.utils.utils import construct_job_description_for_llm

        job_desc_record = session.exec(
            select(models.JobDescription).where(
                models.JobDescription.job_id == create_job_details.job_id
            )
        ).first()

        # Extract values
        job_title = create_job_details.job_title

        # Combine work details as job info
        info_parts = []
        if create_job_details.location:
            info_parts.append(create_job_details.location)
        if create_job_details.country:
            info_parts.append(create_job_details.country)
        if create_job_details.work_mode:
            info_parts.append(create_job_details.work_mode)
        if create_job_details.employment_type:
            info_parts.append(create_job_details.employment_type)
        job_info = ", ".join(info_parts) if info_parts else None

        # Extract job_description
        job_description = ""
        if job_desc_record and job_desc_record.description:
            if isinstance(job_desc_record.description, list):
                desc_parts = []
                for item in job_desc_record.description:
                    if isinstance(item, dict):
                        title = item.get("title") or item.get("section_title") or item.get("heading")
                        content = item.get("content") or item.get("text") or item.get("value")
                        if title and content:
                            desc_parts.append(f"{title}: {content}")
                        elif content:
                            desc_parts.append(content)
                        else:
                            desc_parts.append(", ".join(f"{k}: {v}" for k, v in item.items() if v))
                    elif isinstance(item, str):
                        desc_parts.append(item)
                job_description = "\n".join(desc_parts)
            elif isinstance(job_desc_record.description, str):
                job_description = job_desc_record.description

        # Extract job_requirements
        req_parts = []
        if create_job_details.min_experience is not None or create_job_details.max_experience is not None:
            exp_str = ""
            if create_job_details.min_experience is not None and create_job_details.max_experience is not None:
                exp_str = f"{create_job_details.min_experience} to {create_job_details.max_experience} years experience"
            elif create_job_details.min_experience is not None:
                exp_str = f"Minimum {create_job_details.min_experience} years experience"
            else:
                exp_str = f"Maximum {create_job_details.max_experience} years experience"
            req_parts.append(exp_str)
        if create_job_details.certifications_required:
            req_parts.append(f"Certifications: {create_job_details.certifications_required}")
        if create_job_details.languages:
            req_parts.append(f"Languages: {create_job_details.languages}")
        if create_job_details.additional_notes:
            req_parts.append(f"Notes: {create_job_details.additional_notes}")
        job_requirements = "\n".join(req_parts) if req_parts else None

        # Extract qualification
        qualification = create_job_details.education_requirements

        # Extract skills
        skills = create_job_details.skills_must_have
        if create_job_details.nice_to_have_skills:
            skills = f"{skills or ''}\nNice to have: {create_job_details.nice_to_have_skills}"

        job_description_for_llm = construct_job_description_for_llm(
            job_title=job_title,
            job_info=job_info,
            job_description=job_description,
            job_requirements=job_requirements,
            qualification=qualification,
            skills=skills,
        )
        context = {
            "job_title": job_title,
            "job_description": job_description_for_llm,
            "experience_level": resume_analysis.experience_level if resume_analysis else "Intermediate",
            "skills": skills,
            "interview_focus_areas": resume_analysis.interview_focus_areas if resume_analysis else [],
            "resume_text": resume_text,
        }
        return context
    except Exception as e:
        logger.error(f"Error getting interview context: {str(e)}")
        return None


def get_job_title(session: Session, job_id: int):
    create_job_details = (
        session.exec(select(models.CreateJobDetails).where(models.CreateJobDetails.job_id == job_id))
        .first()
    )
    return create_job_details.job_title if create_job_details else None


def get_candidate_name(session: Session, application_id: int):
    job_application = session.exec(
        select(models.JobApplications).where(
            models.JobApplications.id == application_id
        )
    ).first()

    candidate_name = job_application.first_name + " " + job_application.last_name

    return candidate_name


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
            resume_analysis_update.updated_at = timezone_utils.get_ist_now()
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
