import logging
from datetime import datetime
from sqlmodel import Session, select
import app.models as models
from app.core import config as consts
import re
from app.utils import timezone_utils

logger = logging.getLogger(__name__)


# --- RESUME ANALYSIS SERVICE ---


class ResumeAnalysisService:

    @staticmethod
    def save_analysis_to_database(session: Session, data):
        try:
            result = ResumeAnalysisService._save_single_candidate(session, data)
            return result
        except Exception as e:
            logger.error(f"Error saved analysis to database: {str(e)}")
            raise

    @staticmethod
    def _save_single_candidate(session: Session, candidate_data):
        application_id = candidate_data.get("application_id")
        if not application_id:
            first_name = candidate_data.get("first_name", "")
            last_name = candidate_data.get("last_name", "")
            email = candidate_data.get("email", "")
            candidate_name = str(first_name) + " " + str(last_name)
            application = ResumeAnalysisService._find_application(
                session, first_name, last_name, email
            )
            if not application:
                raise ValueError(
                    consts.JOB_APPLICATION_NOT_FOUND_FOR_NAME_AND_EMAIL(
                        candidate_name, email
                    )
                )
        else:
            application = session.exec(
                select(models.JobApplications).where(
                    models.JobApplications.id == application_id
                )
            ).first()
            if not application:
                raise ValueError(
                    consts.JOB_APPLICATION_NOT_FOUND_FOR_ID(application_id)
                )
        analysis_data = ResumeAnalysisService._prepare_analysis_data(
            candidate_data, application
        )
        statement = select(models.ResumeAnalysis).where(
            models.ResumeAnalysis.application_id == application.id
        )
        analysis = session.exec(statement).first()
        created = False
        if analysis:
            for key, value in analysis_data.items():
                setattr(analysis, key, value)
        else:
            analysis = models.ResumeAnalysis(**analysis_data)
            created = True
        # Always derive status from the final score
        analysis.status = "Shortlisted" if analysis.final_score > 50 else "Not Shortlisted"
        session.add(analysis)
        session.commit()
        session.refresh(analysis)
        session.add(application)
        session.commit()
        return {"updated": not created, "analysis": analysis}

    @staticmethod
    def _find_application(session: Session, first_name, last_name, email):
        try:
            statement = select(models.JobApplications).where(
                models.JobApplications.first_name == first_name,
                models.JobApplications.last_name == last_name,
                models.JobApplications.email == email,
            )
            results = session.exec(statement).all()
            if results:
                if len(results) == 1:
                    return results[0]
                else:
                    logger.debug(
                        f"Warning: Multiple exact matches for {first_name + ' ' + last_name} ({email})"
                    )
                    return results[0]
            statement = select(models.JobApplications).where(
                models.JobApplications.first_name == first_name,
                models.JobApplications.email == email,
            )
            results = session.exec(statement).all()
            if results:
                if len(results) == 1:
                    return results[0]
                else:
                    logger.debug(
                        f"Warning: Multiple matches for {first_name + ' ' + last_name} ({email}), returning first match"
                    )
                    return results[0]
            statement = select(models.JobApplications).where(
                models.JobApplications.email == email
            )
            results = session.exec(statement).all()
            if results:
                logger.debug(
                    f"Warning: Using email-only match for {first_name + ' ' + last_name} ({email})"
                )
                return results[0]
            logger.debug(
                f"No matching application found for {first_name + ' ' + last_name} ({email})"
            )
            return None
        except Exception as e:
            logger.error(
                f"Error finding application for {first_name + ' ' + last_name}: {e}"
            )
            return None

    @staticmethod
    def _prepare_analysis_data(candidate_data, application):
        scores = candidate_data.get("scores", {})
        recommendation = candidate_data.get("recommendation", {})
        skills_analysis = candidate_data.get("skills_analysis", {})
        experience_analysis = candidate_data.get("experience_analysis", {})
        education_analysis = candidate_data.get("education_analysis", {})
        job_analysis = candidate_data.get("job_analysis", {})
        assessment = candidate_data.get("assessment", {})
        hiring_insights = candidate_data.get("hiring_insights", {})
        metadata = candidate_data.get("metadata", {})
        processed_at = metadata.get("processed_at")
        if processed_at:
            try:
                if isinstance(processed_at, str):
                    processed_at = timezone_utils.parse_datetime_to_ist(
                        processed_at.replace("Z", "+00:00")
                    )
                elif not isinstance(processed_at, datetime):
                    processed_at = timezone_utils.get_ist_now()
            except:
                processed_at = timezone_utils.get_ist_now()
        else:
            processed_at = timezone_utils.get_ist_now()
        return {
            "application_id": application.id,
            "job_id": application.job_id,
            "candidate_name": candidate_data.get("candidate_name", ""),
            "email": candidate_data.get("email", ""),
            "contact_number": candidate_data.get("contact_number", ""),
            "final_score": scores.get("final_score", 0),
            "skills_match": scores.get("skills_match", 0),
            "experience_score": scores.get("experience_score", 0),
            "education_score": scores.get("education_score", 0),
            "keywords_match": scores.get("keywords_match", 0),
            "overall_fit": scores.get("overall_fit", 0),
            "growth_potential": scores.get("growth_potential", 0),
            "recommendation_decision": recommendation.get("decision", ""),
            "recommendation_reason": recommendation.get("reason", ""),
            "recommendation_confidence": recommendation.get("confidence", ""),
            "skill_match_percentage": skills_analysis.get("skill_match_percentage", 0),
            "tb_matching_skills": skills_analysis.get("tb_matching_skills", []),
            "tb_missing_skills": skills_analysis.get("tb_missing_skills", []),
            "experience_level": experience_analysis.get("experience_level", ""),
            "tb_matching_experience": experience_analysis.get("tb_matching_experience", []),
            "tb_experience_gaps": experience_analysis.get("tb_experience_gaps", []),
            "education_level": education_analysis.get("education_level", ""),
            "tb_education_highlights": education_analysis.get("tb_education_highlights", []),
            "is_fresher": job_analysis.get("fresher", True),
            "first_job_start_year": job_analysis.get("first_job_start_year"),
            "last_job_end_year": job_analysis.get("last_job_end_year"),
            "total_jobs_count": job_analysis.get("total_jobs_count", 0),
            "average_job_change": job_analysis.get("average_job_change"),
            "tb_strengths": assessment.get("tb_strengths", []),
            "tb_weaknesses": assessment.get("tb_weaknesses", []),
            "tb_red_flags": assessment.get("tb_red_flags", []),
            "tb_cultural_fit_indicators": assessment.get("tb_cultural_fit_indicators", []),
            "salary_expectation_alignment": hiring_insights.get(
                "salary_expectation_alignment", ""
            ),
            "onboarding_priority": hiring_insights.get("onboarding_priority", ""),
            "tb_interview_focus_areas": hiring_insights.get("tb_interview_focus_areas", []),
            "processing_time": metadata.get("processing_time", 0),
            "processed_at": processed_at,
            "file_path": ResumeAnalysisService._extract_relative_path(
                metadata.get("file_path", "")
            ),
            "file_size": metadata.get("file_size", 0),
            "word_count": metadata.get("word_count", 0),
            "success": metadata.get("success", True),
            "error_message": metadata.get("error"),
        }

    @staticmethod
    def _extract_relative_path(full_path):
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
