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
    def save_dummy_analysis(session: Session, application_id: int):
        application = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == application_id
            )
        ).first()
        if not application:
            raise ValueError(consts.JOB_APPLICATION_NOT_FOUND_FOR_ID(application_id))

        # Fetch job details from tb_create_job_details
        job_details = None
        if application.job_id:
            job_details = session.exec(
                select(models.CreateJobDetails).where(
                    models.CreateJobDetails.job_id == application.job_id
                )
            ).first()

        # Candidate details from tb_job_applications
        cand_first = (application.first_name or "").strip()
        cand_last = (application.last_name or "").strip()
        candidate_name = f"{cand_first} {cand_last}".strip()
        if not candidate_name or candidate_name.lower() in ["none", "null", "unknown"]:
            candidate_name = "Candidate"
        email = (application.email or "").strip()
        contact_number = (application.ph_no or "").strip()
        file_path = application.resume or ""

        # Job details from tb_create_job_details
        job_title = (job_details.job_title if job_details and job_details.job_title else "Position").strip()
        
        # Parse skills
        matching_skills = []
        if job_details and job_details.skills_must_have:
            matching_skills = [s.strip() for s in re.split(r'[,;\n/]+', job_details.skills_must_have) if s.strip()]
        if not matching_skills and job_details and job_details.nice_to_have_skills:
            matching_skills = [s.strip() for s in re.split(r'[,;\n/]+', job_details.nice_to_have_skills) if s.strip()]
        if not matching_skills:
            matching_skills = ["Technical Proficiency", "Problem Solving", "Collaboration", "Domain Knowledge"]

        missing_skills = []
        if job_details and job_details.nice_to_have_skills:
            nice_skills = [s.strip() for s in re.split(r'[,;\n/]+', job_details.nice_to_have_skills) if s.strip()]
            missing_skills = [s for s in nice_skills if s not in matching_skills][:2]

        # Experience details
        min_exp = job_details.min_experience if job_details and job_details.min_experience is not None else 3
        max_exp = job_details.max_experience if job_details and job_details.max_experience is not None else 6
        if min_exp >= 5:
            experience_level = "Senior"
        elif min_exp >= 2:
            experience_level = "Intermediate"
        elif min_exp > 0:
            experience_level = "Beginner"
        else:
            experience_level = "Fresher"

        # Education details
        edu_req = (job_details.education_requirements if job_details and job_details.education_requirements else "Bachelor's Degree in related field").strip()
        edu_lower = edu_req.lower()
        if any(w in edu_lower for w in ["master", "m.tech", "ms", "mba", "post graduate"]):
            education_level = "Master"
        elif any(w in edu_lower for w in ["bachelor", "b.tech", "b.e", "bs", "degree", "graduate"]):
            education_level = "Bachelor"
        else:
            education_level = "Graduate"

        # Certifications
        certifications = []
        if job_details and job_details.certifications_required:
            certifications = [c.strip() for c in re.split(r'[,;\n]+', job_details.certifications_required) if c.strip()]

        # Languages
        languages = []
        if job_details and job_details.languages:
            languages = [l.strip() for l in re.split(r'[,;\n]+', job_details.languages) if l.strip()]
        if not languages:
            languages = ["English"]

        location = (job_details.location if job_details and job_details.location else "Not Mentioned").strip()

        candidate_payload = {
            "application_id": application.id,
            "job_id": application.job_id,
            "candidate_name": candidate_name,
            "email": email,
            "contact_number": contact_number,
            "scores": {
                "final_score": 85.0,
                "skills_match": 88.0,
                "experience_score": 85.0,
                "education_score": 85.0,
                "keywords_match": 82.0,
                "overall_fit": 86.0,
                "growth_potential": 85.0,
            },
            "recommendation": {
                "decision": "HIRE",
                "reason": f"Candidate profile demonstrates strong alignment with {job_title} requirements.",
                "confidence": "High",
            },
            "skills_analysis": {
                "skill_match_percentage": 88.0,
                "tb_matching_skills": matching_skills,
                "tb_missing_skills": missing_skills,
            },
            "experience_analysis": {
                "experience_level": experience_level,
                "tb_matching_experience": [
                    f"{min_exp}+ years of experience relevant to {job_title}",
                    "Requirement analysis and execution",
                    "Cross-functional team collaboration",
                ],
                "tb_experience_gaps": [f"Deep specialization in {missing_skills[0]}"] if missing_skills else [],
            },
            "education_analysis": {
                "education_level": education_level,
                "tb_education_highlights": [
                    edu_req,
                    "Relevant academic coursework and foundational domain knowledge",
                ],
                "tb_matching_education": [edu_req],
                "tb_missing_education": [],
            },
            "job_analysis": {
                "fresher": (min_exp == 0),
                "first_job_start_year": 2020 if min_exp > 0 else 2024,
                "last_job_end_year": 2025,
                "total_jobs_count": 2 if min_exp > 0 else 0,
                "average_job_change": "2.5 years" if min_exp > 0 else None,
            },
            "assessment": {
                "tb_strengths": [
                    f"Strong technical aptitude for {job_title}",
                    "Demonstrated alignment with required core capabilities",
                    "Strong problem-solving and communication skills",
                ],
                "tb_weaknesses": [f"Secondary proficiency in {missing_skills[0]}"] if missing_skills else [],
                "tb_red_flags": [],
                "tb_cultural_fit_indicators": [
                    "Collaborative",
                    "Adaptable",
                    "Clear Communicator",
                ],
            },
            "hiring_insights": {
                "salary_expectation_alignment": "Aligned",
                "onboarding_priority": "High",
                "tb_interview_focus_areas": matching_skills[:3] if matching_skills else [f"{job_title} Core Concepts"],
            },
            "metadata": {
                "processing_time": 2.5,
                "processed_at": timezone_utils.format_datetime_for_api(timezone_utils.get_ist_now()),
                "file_path": file_path,
                "file_size": 102400,
                "word_count": 500,
                "success": True,
                "error": None,
            },
            # Applicant update details
            "name": candidate_name,
            "designation": job_title,
            "current_location": location,
            "total_experience": f"{min_exp} Years" if min_exp else "Fresher",
            "phone_no": contact_number,
            "personal_languages_known": languages,
            "personal_address": location,
            "education_details": [
                {
                    "degree": edu_req,
                    "institution": "University / Institute",
                    "field_of_study": job_title,
                    "start_year": 2016 if min_exp > 0 else 2020,
                    "end_year": 2020 if min_exp > 0 else 2024,
                    "percentage": "80%"
                }
            ],
            "experience_details": [
                {
                    "job_title": job_title,
                    "company": "Previous Tech Organization",
                    "start_date": "2020" if min_exp > 0 else "2024",
                    "end_date": "2025",
                    "description": [f"Contributed to key modules using {s}" for s in matching_skills[:3]]
                }
            ] if min_exp > 0 else [],
            "projects": [
                {
                    "project_title": f"{job_title} Project",
                    "description": [f"Engineered and delivered core functionality using {', '.join(matching_skills[:3])}"],
                    "tech_stack": matching_skills[:4],
                    "start_date": "2022" if min_exp > 0 else "2024",
                    "end_date": "2024"
                }
            ],
            "certifications": certifications,
            "total_projects_count": 1,
        }

        # Save to tb_resume_attributes
        try:
            from app.services.db_operations import create_or_update_resume_attributes_db, create_or_update_resume_analysis_update_db
            create_or_update_resume_attributes_db(session, application.id, candidate_payload, True)
            create_or_update_resume_analysis_update_db(session, application.id, candidate_payload)
        except Exception as e:
            logger.warning(f"Failed to save auxiliary resume tables during dummy bypass: {e}")

        return ResumeAnalysisService._save_single_candidate(
            session,
            candidate_payload
        )

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

        # Fallback candidate info from tb_job_applications
        app_cand_name = f"{(application.first_name or '').strip()} {(application.last_name or '').strip()}".strip()
        cand_name = candidate_data.get("candidate_name") or candidate_data.get("name")
        if not cand_name or str(cand_name).strip().lower() in ["", "no name found", "not mentioned", "none", "null", "unknown"]:
            cand_name = app_cand_name if app_cand_name else "Candidate"

        email = candidate_data.get("email")
        if not email or str(email).strip().lower() in ["", "no email found", "not mentioned", "none", "null", "unknown"]:
            email = application.email or ""

        contact_number = candidate_data.get("contact_number") or candidate_data.get("phone_no") or candidate_data.get("phone")
        if not contact_number or str(contact_number).strip().lower() in ["", "not mentioned", "none", "null", "unknown"]:
            contact_number = application.ph_no or ""

        raw_file_path = metadata.get("file_path") or application.resume or ""
        file_path = ResumeAnalysisService._extract_relative_path(raw_file_path)

        tb_matching_education = education_analysis.get("tb_matching_education", [])
        tb_education_highlights = education_analysis.get("tb_education_highlights", [])
        if not tb_matching_education and tb_education_highlights:
            tb_matching_education = tb_education_highlights

        return {
            "application_id": application.id,
            "job_id": application.job_id,
            "candidate_name": cand_name,
            "email": email,
            "contact_number": contact_number,
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
            "tb_education_highlights": tb_education_highlights,
            "tb_matching_education": tb_matching_education,
            "tb_missing_education": education_analysis.get("tb_missing_education", []),
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
            "file_path": file_path,
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
