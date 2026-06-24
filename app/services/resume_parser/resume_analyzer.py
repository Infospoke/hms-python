import logging
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
from app.utils.timezone_utils import get_ist_now
from sqlmodel import Session, select
from .s3_resume_parser import S3ResumeParser
from .scoring_engine import ScoringEngine
from ..db_operations import *
from .resume_analysis_service import ResumeAnalysisService
import app.models as models
from app.core.exceptions import ResumeParsingException
import app.core.config as consts
from app.core import messages
from app.services.email.interview_emails import send_resume_result_email
from app.services.email.email_service import get_candidate_details
import time
import re
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- RESUME ANALYZER ---


class ResumeAnalyzer:

    def __init__(self, session: Session, job_title, background_tasks=None):
        self.resume_parser = S3ResumeParser()
        self.scoring_engine = ScoringEngine()
        self.job_title = job_title
        self.session = session
        self.file_to_app_id_map = {}
        self.background_tasks = background_tasks
        logger.info(f"ResumeAnalyzer initialized with background_tasks: {background_tasks is not None}")

    def _analyze_parsed_resume(
        self, resume_file_path: str, parsed_resume: Dict[str, Any], job_description: str
    ) -> Dict[str, Any]:
        try:
            resume_file_name = str(resume_file_path.split("/")[-1])
            scoring_result = self.scoring_engine.score_resume(
                parsed_resume, job_description
            )
            scoring_result["file_path"] = resume_file_path
            logger.info(f"Successfully analyzed resume: {resume_file_name}")
            return scoring_result
        except Exception as e:
            logger.error(f"Error analyzing resume {resume_file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "filename": resume_file_name,
                "final_score": 0,
                "recommendation": "REJECT",
                "file_path": resume_file_path,
            }

    def analyze_single_resume(
        self, resume_file_path: str, job_description: str
    ) -> Dict[str, Any]:
        try:
            resume_file_name = str(resume_file_path.split("/")[-1])

            parsed_resume = self.resume_parser.parse_resume(resume_file_path)
            if not parsed_resume["success"]:
                logger.warning(
                    f"Failed to parse resume {resume_file_name}: {parsed_resume['error']}"
                )
                raise ResumeParsingException(resume_file_name, parsed_resume["error"])
            return self._analyze_parsed_resume(
                resume_file_path, parsed_resume, job_description
            )
        except ResumeParsingException:
            raise
        except FileNotFoundError as e:
            logger.error(f"File error analyzing resume: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "filename": resume_file_name,
                "final_score": 0,
                "recommendation": "REJECT",
                "file_path": resume_file_path,
            }
        except Exception as e:
            logger.error(f"Error analyzing resume {resume_file_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "filename": resume_file_name,
                "final_score": 0,
                "recommendation": "REJECT",
                "file_path": resume_file_path,
            }

    def analyze_multiple_resumes(
        self,
        resume_files: List[str],
        job_description: str,
        progress_callback: Optional[callable] = None,
        app_id_map: Dict[str, int] = None,
    ) -> Dict[str, Any]:
        BATCH_SIZE = consts.RESUME_BATCH_SIZE
        BATCH_WINDOW = 55.0
        if app_id_map:
            self.file_to_app_id_map = app_id_map
        results = []
        total_files = len(resume_files)
        errors = 0
        logger.info(f"Analyzing {total_files} resumes sequentially")
        time.time()
        if total_files == 0:
            logger.warning(messages.NO_RESUME_FILES_PROVIDED)
            return {
                "success": False,
                "error": messages.NO_RESUME_FILES_ERROR,
                "results": [],
                "statistics": {},
            }
        i = 0
        current_window_tokens = 0
        window_start_time = time.time()
        while i < total_files:
            elapsed_start = time.time() - window_start_time
            if elapsed_start >= BATCH_WINDOW:
                current_window_tokens = 0
                window_start_time = time.time()
            candidates_indices = range(i, min(i + BATCH_SIZE, total_files))
            candidates_parsed = []
            for idx in candidates_indices:
                file_path = resume_files[idx]
                try:
                    parsed = self.resume_parser.parse_resume(file_path)
                    if not parsed["success"]:
                        candidates_parsed.append((file_path, parsed, 0))
                    else:
                        text = parsed.get("text", "")
                        cost = self.scoring_engine.estimate_cost(text, job_description)
                        candidates_parsed.append((file_path, parsed, cost))
                except Exception as e:
                    candidates_parsed.append(
                        (file_path, {"success": False, "error": str(e)}, 0)
                    )
            final_batch_items = []
            TOKEN_LIMIT_SOFT = 12000
            TOKEN_LIMIT_HARD = 13000
            WINDOW_TOKEN_LIMIT = 12000
            while len(candidates_parsed) > 0:
                current_batch_cost = sum(item[2] for item in candidates_parsed)
                if current_batch_cost < TOKEN_LIMIT_SOFT:
                    final_batch_items = candidates_parsed
                    if current_window_tokens + current_batch_cost > WINDOW_TOKEN_LIMIT:
                        pass
                    break
                elif len(candidates_parsed) == 1:
                    final_batch_items = candidates_parsed
                    break
                else:
                    candidates_parsed.pop()
            final_batch_cost = sum(item[2] for item in final_batch_items)
            if current_window_tokens + final_batch_cost > WINDOW_TOKEN_LIMIT:
                elapsed = time.time() - window_start_time
                sleep_needed = max(0, BATCH_WINDOW - elapsed)
                time.sleep(sleep_needed)
                current_window_tokens = 0
                window_start_time = time.time()
            processed_futures = []
            items_to_process = final_batch_items
            total_batch_tokens = sum(item[2] for item in items_to_process)
            run_parallel = total_batch_tokens < TOKEN_LIMIT_SOFT
            valid_items_to_process = []
            for file_path, parsed_data, cost in items_to_process:
                if not parsed_data.get("success"):
                    errors = self._handle_parse_error(
                        file_path, parsed_data.get("error"), results, errors
                    )
                else:
                    valid_items_to_process.append((file_path, parsed_data, cost))
            if valid_items_to_process:
                if run_parallel:
                    with ThreadPoolExecutor(
                        max_workers=len(valid_items_to_process)
                    ) as executor:
                        for file_path, parsed_data, _ in valid_items_to_process:
                            future = executor.submit(
                                self._analyze_parsed_resume,
                                file_path,
                                parsed_data,
                                job_description,
                            )
                            processed_futures.append((future, file_path))
                else:
                    current_minute_tokens = 0
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        for file_path, parsed_data, cost in valid_items_to_process:
                            if current_minute_tokens + cost > TOKEN_LIMIT_HARD:
                                time.sleep(55)
                                current_minute_tokens = 0
                            future = executor.submit(
                                self._analyze_parsed_resume,
                                file_path,
                                parsed_data,
                                job_description,
                            )
                            processed_futures.append((future, file_path))
                            current_minute_tokens += cost
            for future, file_path in processed_futures:
                try:
                    result = future.result()
                    errors = self._process_analysis_result(
                        result,
                        file_path,
                        results,
                        progress_callback,
                        total_files,
                        errors,
                    )
                except Exception as e:
                    logger.error(f"Error in future result: {e}")
                    err_msg = str(e)
                    results.append(
                        {
                            "success": False,
                            "error": err_msg,
                            "filename": (
                                Path(file_path).name if file_path else "unknown"
                            ),
                        }
                    )
                    normalized_path = file_path.replace("\\", "/")
                    realtive_path = self._extract_relative_path(file_path)
                    application_id = (
                        self.file_to_app_id_map.get(realtive_path)
                        or self.file_to_app_id_map.get(normalized_path)
                        or self.file_to_app_id_map.get(file_path.replace("/", "\\"))
                    )
                    errors += 1
            num_processed = len(items_to_process)
            i += num_processed
            current_window_tokens += sum(item[2] for item in items_to_process)
            elapsed = time.time() - window_start_time
            if elapsed >= BATCH_WINDOW:
                current_window_tokens = 0
                window_start_time = time.time()
        statistics = self._calculate_statistics(results)
        if errors == len(resume_files):
            return {
                "success": False,
                "results": results,
                "job_description": job_description,
            }
        return {
            "success": True,
            "results": results,
            "statistics": statistics,
            "job_description": job_description,
        }

    def _extract_basic_metadata(self, text: str) -> Dict[str, Any]:
        metadata = {
            "word_count": len(text.split()),
            "has_email": bool(
                re.search(
                    "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b", text
                )
            ),
            "has_phone": bool(
                re.search(
                    "(\\+\\d{1,3}[-.\\s]?)?\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}",
                    text,
                )
            ),
            "has_linkedin": "linkedin" in text.lower(),
            "has_github": "github" in text.lower(),
            "candidate_name": self._extract_name(text),
        }
        return metadata

    def _extract_name(self, text: str) -> str:
        lines = text.strip().split("\n")
        if lines:
            first_line = lines[0].strip()
            if len(first_line.split()) >= 2 and len(first_line) < 50:
                return first_line
        return messages.NAME_NOT_FOUND

    def _calculate_statistics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_resumes = len(results)
        successful_results = [r for r in results if r.get("success", False)]
        failed_results = [r for r in results if not r.get("success", False)]
        if not successful_results:
            return {
                "total_resumes": total_resumes,
                "successful": 0,
                "failed": len(failed_results),
                "average_score": 0,
                "recommendations": {"HIRE": 0, "CONSIDER": 0, "REJECT": total_resumes},
            }
        scores = [r.get("final_score", 0) for r in successful_results]
        average_score = sum(scores) / len(scores) if scores else 0
        recommendations = {"HIRE": 0, "CONSIDER": 0, "REJECT": 0}
        for result in results:
            rec = result.get("recommendation", {}).get("decision", "REJECT")
            recommendations[rec] = recommendations.get(rec, 0) + 1
        return {
            "total_resumes": total_resumes,
            "successful": len(successful_results),
            "failed": len(failed_results),
            "average_score": round(average_score, 2),
            "recommendations": recommendations,
        }

    def structure_web_json(self, result, application_id=None):
        analysis = result.get("analysis", {}) if result.get("success") else {}
        metadata = result.get("metadata", {})
        filename = result.get("filename", "")
        job = []
        if application_id:
            job_app = get_job_application_by_id(self.session, application_id)
            if job_app:
                job = [job_app]
        if not job:
            file_path = result.get("file_path", "")
            statement = select(models.JobApplications).where(
                models.JobApplications.resume == file_path
            )
            job = self.session.exec(statement).all()
        metadata_candidate_name = metadata.get("candidate_name")
        candidate_name_final = (
            metadata_candidate_name
            if metadata_candidate_name and metadata_candidate_name != "Name not found"
            else (
                job[0].first_name + " " + (job[0].last_name or "")
                if job
                else "No name found"
            )
        )
        parser_email = result.get("email")
        email_final = (
            parser_email if parser_email else job[0].email if job else "No email found"
        )
        parser_phone = result.get("contact_number") or result.get("phone")
        phone_final = (
            parser_phone if parser_phone else job[0].ph_no if job else "No contact"
        )
        web_result = {
            "success": True,
            "filename": result.get("filename", ""),
            "candidate_name": candidate_name_final,
            "email": email_final,
            "contact_number": phone_final,
            "scores": {
                "final_score": self._safe_round(result.get("final_score", 0), 2),
                "skills_match": self._safe_round(
                    result.get("scores", {}).get("skills_match", 0), 2
                ),
                "experience_score": self._safe_round(
                    result.get("scores", {}).get("experience_relevance", 0), 2
                ),
                "education_score": self._safe_round(
                    result.get("scores", {}).get("education", 0), 2
                ),
                "keywords_match": self._safe_round(
                    result.get("scores", {}).get("keywords_match", 0), 2
                ),
                "overall_fit": self._safe_round(
                    result.get("scores", {}).get("overall_fit", 0), 2
                ),
                "growth_potential": self._safe_round(
                    analysis.get("growth_potential", 0), 2
                ),
            },
            "recommendation": {
                "decision": result.get("recommendation", "REJECT"),
                "reason": analysis.get("recommendation_reason", ""),
                "confidence": (
                    "HIGH"
                    if result.get("final_score", 0) > 80
                    else "MEDIUM" if result.get("final_score", 0) > 60 else "LOW"
                ),
            },
            "skills_analysis": {
                "matching_skills": analysis.get("matching_skills", []),
                "missing_skills": analysis.get("missing_skills", []),
                "skill_match_percentage": self._safe_round(
                    len(analysis.get("matching_skills", []))
                    / max(
                        len(analysis.get("matching_skills", []))
                        + len(analysis.get("missing_skills", [])),
                        1,
                    )
                    * 100,
                    2,
                ),
            },
            "experience_analysis": {
                "matching_experience": analysis.get("matching_experience", []),
                "experience_gaps": analysis.get("experience_gaps", []),
                "experience_level": (
                    "Experienced"
                    if result.get("scores", {}).get("experience_relevance", 0) > 80
                    else (
                        "Intermediate"
                        if result.get("scores", {}).get("experience_relevance", 0) > 60
                        else "Beginner"
                    )
                ),
            },
                "education_analysis": {
                   "education_highlights": analysis.get("education_highlights", []),
                    "matching_education": analysis.get("matching_education", []),
                    "missing_education": analysis.get("missing_education", []),
                     "education_level": (
                        "ADVANCED"
                        if result.get("scores", {}).get("education", 0) > 80
                        else (
                            "STANDARD"
                            if result.get("scores", {}).get("education", 0) > 60
                            else "BASIC"
                        )
                    ),
            },
            "job_analysis": {
                "fresher": analysis.get("fresher", "true"),
                "first_job_start_year": (
                    analysis.get("first_job_start_year", "null")
                    if analysis.get("fresher", True) == False
                    else 0
                ),
                "last_job_end_year": (
                    analysis.get("last_job_end_year", "null")
                    if analysis.get("fresher", True) == False
                    else 0
                ),
                "total_jobs_count": (
                    analysis.get("total_jobs_count", "null")
                    if analysis.get("fresher", True) == False
                    else 0
                ),
                "average_job_change": self.getAverageJobChange(
                    analysis.get("fresher", "true"),
                    analysis.get("first_job_start_year", "null"),
                    analysis.get("last_job_end_year", "null"),
                    analysis.get("total_jobs_count", "null"),
                ),
            },
            "assessment": {
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", []),
                "red_flags": analysis.get("red_flags", []),
                "cultural_fit_indicators": analysis.get("cultural_fit_indicators", []),
            },
            "hiring_insights": {
                "salary_expectation_alignment": analysis.get(
                    "salary_expectation_alignment", "MEDIUM"
                ),
                "interview_focus_areas": analysis.get("interview_focus_areas", []),
                "onboarding_priority": (
                    "HIGH"
                    if result.get("recommendation") == "HIRE"
                    else (
                        "MEDIUM"
                        if result.get("recommendation") == "CONSIDER"
                        else "LOW"
                    )
                ),
            },
            "metadata": {
                "processing_time": self._safe_round(
                    result.get("processing_time", 0), 2
                ),
                "processed_at": result.get(
                    "timestamp", timezone_utils.format_datetime_for_api(get_ist_now())
                ),
                "file_path": self._extract_relative_path(
                    str(result.get("file_path", ""))
                ),
                "file_size": self._safe_round(metadata.get("file_size", 0), 5),
                "word_count": metadata.get("word_count", 0),
                "success": result.get("success", False),
                "error": (
                    result.get("error", "")
                    if not result.get("success", False)
                    else None
                ),
            },
            "summary": result.get("summary", ""),
            "analysis": result.get("analysis", {}),
        }
        return web_result

    def _safe_round(self, value, decimals=2):
        try:
            return round(float(value), decimals)
        except (ValueError, TypeError):
            return 0.0

    def getAverageJobChange(
        self, fresher, first_job_start_year, last_job_end_year, total_jobs_count
    ):
        if fresher:
            return "No job changes"
        elif (
            first_job_start_year != "null"
            and last_job_end_year != "null"
            and total_jobs_count != "null"
            and total_jobs_count > 0
        ):
            try:
                start_year = int(first_job_start_year)
                end_year = int(last_job_end_year)
                if start_year == 0 or end_year == 0:
                    return "No job changes"
                job_count = int(total_jobs_count)
                if job_count <= 1:
                    return "No job changes"
                total_career_years = max(1, end_year - start_year)
                average_time_per_job = total_career_years / job_count
                years = int(average_time_per_job)
                months = int((average_time_per_job - years) * 12)
                if years == 0 and months == 0:
                    return messages.LESS_THAN_ONE_MONTH
                elif years == 0:
                    return f"{months} month{'s' if months != 1 else ''}"
                elif months == 0:
                    return f"{years} year{'s' if years != 1 else ''}"
                else:
                    return f"{years} year{'s' if years != 1 else ''} {months} month{'s' if months != 1 else ''}"
            except (ValueError, TypeError):
                return "No job changes"
        else:
            return "No job changes"

    def writeResultToTextFile(self, result):
        with open("test.txt", "w") as fp:
            fp.write(json.dumps(result, indent=2))

    def _handle_parse_error(self, file_path, error_msg, results, errors):
        filename = Path(file_path).name
        result = {
            "success": False,
            "error": error_msg,
            "filename": filename,
            "file_path": file_path,
        }
        normalized_path = file_path.replace("\\", "/")
        realtive_path = self._extract_relative_path(file_path)
        application_id = (
            self.file_to_app_id_map.get(realtive_path)
            or self.file_to_app_id_map.get(normalized_path)
            or self.file_to_app_id_map.get(file_path.replace("/", "\\"))
        )
        results.append(result)
        return errors + 1

    def _process_analysis_result(
        self, result, file_path, results, progress_callback, total_files, errors
    ):
        filename = result.get("filename", Path(file_path).name)
        success = result.get("success", False)
        normalized_path = file_path.replace("\\", "/")
        realtive_path = self._extract_relative_path(file_path)
        application_id = (
            self.file_to_app_id_map.get(realtive_path)
            or self.file_to_app_id_map.get(normalized_path)
            or self.file_to_app_id_map.get(file_path.replace("/", "\\"))
        )
        if not application_id:
            logger.warning(f"No application ID found for file: {file_path}")
            success = False
            result["success"] = False
            result["error"] = f"No application ID mapping for {filename}"
            results.append(result)
            return errors + 1
        log_resume_activity(
            self.session,
            application_id,
            "STARTED",
            f"Starting analysis for {filename}",
            "ResumeAnalyzer",
        )
        if not success:
            log_resume_activity(
                self.session,
                application_id,
                "FAILED",
                f"Analysis failed: {result.get('error')}",
                "ResumeAnalyzer",
            )
            result["application_id"] = application_id
            results.append(result)
            return errors + 1
        web_json_data = self.structure_web_json(result, application_id)
        web_json_data["application_id"] = application_id
        try:
            resume_attribute = create_or_update_json_analysis_db(
                self.session, application_id, web_json_data, success
            )
            if resume_attribute:
                summary = ResumeAnalysisService.save_analysis_to_database(
                    self.session, json.loads(resume_attribute.analysis_json)
                )
                result_web_data = json.loads(resume_attribute.analysis_json)
                results.append(result_web_data)
                log_resume_activity(
                    self.session,
                    application_id,
                    "SUCCESS",
                    messages.ANALYSIS_COMPLETED_AND_SAVED,
                    "ResumeAnalyzer",
                )

                is_selected = result.get("final_score", 0) >= 50
                if is_selected:
                    try:
                        logger.info(f"Application {application_id} selected (score: {result.get('final_score', 0)}). Auto-creating interview session.")
                        
                        from uuid import uuid4
                        existing_session = self.session.exec(
                            select(models.InterviewSessions).where(
                                models.InterviewSessions.application_id == application_id
                            )
                        ).first()
                        
                        if not existing_session:
                            job_app = self.session.exec(
                                select(models.JobApplications).where(
                                    models.JobApplications.id == application_id
                                )
                            ).first()
                            
                            interview_session_id = str(uuid4())
                            new_session = models.InterviewSessions(
                                interview_session_id=interview_session_id,
                                application_id=application_id,
                                question_type="AI",
                                exam_exit_password="",
                                status=None,
                                job_id=job_app.job_id if job_app else None,
                            )
                            self.session.add(new_session)
                            self.session.flush()
                            
                            existing_analysis = self.session.exec(
                                select(models.InterviewAnalysis).where(
                                    models.InterviewAnalysis.application_id == application_id
                                )
                            ).first()
                            if not existing_analysis:
                                new_analysis = models.InterviewAnalysis(
                                    application_id=application_id,
                                    interview_session_id=interview_session_id,
                                    status=models.StatusEnum.not_started,
                                    questions=[],
                                    job_id=job_app.job_id if job_app else None,
                                )
                                self.session.add(new_analysis)
                            
                            self.session.commit()
                            interview_session = new_session
                        else:
                            interview_session = existing_session

                        if self.background_tasks:
                            from app.services.email.interview_emails import send_interview_invitation
                            send_interview_invitation(
                                interview_session,
                                self.background_tasks,
                                self.session
                            )
                            logger.info(f"Interview invitation sent to candidate for application {application_id}")
                    except Exception as e:
                        logger.error(f"Failed to auto-create interview session/send invite for application {application_id}: {str(e)}")
                else:
                    if self.background_tasks:
                        try:
                            job_title, candidate_name, candidate_email = get_candidate_details(
                                application_id, self.session
                            )
                            send_resume_result_email(
                                candidate_name=candidate_name,
                                candidate_email=candidate_email,
                                job_title=job_title,
                                score=result.get("final_score", 0),
                                is_selected=is_selected,
                                background_tasks=self.background_tasks,
                            )
                            logger.info(f"Rejection email sent to {candidate_email} for application {application_id}")
                        except Exception as e:
                            logger.error(f"Failed to send rejection email for application {application_id}: {str(e)}")

            else:
                logger.warning(messages.FAILED_TO_SAVE_ANALYSIS(filename))
                web_json_data["database_saved"] = False
                web_json_data["error"] = (
                    f"Could not create ResumAttributes for application ID {application_id}"
                )
                results.append(web_json_data)
                log_resume_activity(
                    self.session,
                    application_id,
                    "FAILED",
                    messages.FAILED_TO_SAVE_ATTRIBUTES,
                    "Database",
                )
        except DatabaseQueryException as e:
            logger.error(f"Database error saving analysis for {filename}: {e.message}")
            web_json_data["database_saved"] = False
            web_json_data["error"] = f"Database error: {e.message}"
            results.append(web_json_data)
            log_resume_activity(
                self.session,
                application_id,
                "FAILED",
                f"Database error: {e.message}",
                "Database",
            )
        except Exception as e:
            logger.error(f"Error saving analysis to database for {filename}: {str(e)}")
            web_json_data["database_saved"] = False
            web_json_data["error"] = str(e)
            results.append(web_json_data)
            log_resume_activity(
                self.session,
                application_id,
                "FAILED",
                f"Save error: {str(e)}",
                "Database",
            )
        if progress_callback:
            current_processed = len(results) + errors
            progress_callback(current_processed, total_files, result)
        logger.info(f"Processed {Path(file_path).name}")
        return errors

    def _extract_relative_path(self, full_path):
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