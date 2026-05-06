import json
import logging
from typing import Dict, Any
import re
from .gemini_client import GeminiClient
import app.core.config as consts
from app.core import messages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- RESUME ANALYSIS CLIENT ---


class Client(GeminiClient):

    def __init__(self, model: str = consts.GEMINI_MODEL):
        super().__init__(model)

    def get_token_count(self, text: str) -> int:
        return self.count_tokens(text)

    def analyze_resume(self, resume_text: str, job_description: str) -> Dict[str, Any]:
        resume_text = (resume_text or "").strip()
        if len(resume_text.split()) < 20:
            return {
                "success": False,
                "error": "Insufficient resume text for analysis. Resume content is empty or too short.",
            }
        total_processing_time = 0
        anti_hallucination_rules = (
            "\n\nNON-NEGOTIABLE EVIDENCE RULES:\n"
            "- Use only RESUME text as evidence for candidate details.\n"
            "- Job Description is ONLY for comparison. Never treat JD as candidate history.\n"
            "- If a detail is not explicitly present in RESUME text, return conservative defaults (e.g., 'Name not found', empty arrays, 0 where appropriate).\n"
            "- Never invent names, companies, dates, projects, certifications, or contacts.\n"
            "- If resume lacks sufficient detail, set recommendation to REJECT with reason 'Insufficient resume data'."
        )
        main_system_prompt = consts.MAIN_SYSTEM_PROMPT + anti_hallucination_rules
        user_prompt = consts.USER_PROMPT(job_description, resume_text)
        result = self.generate_response(user_prompt, main_system_prompt)
        total_processing_time += result.get("processing_time", 0)
        if not result.get("success"):
            return {
                "success": False,
                "error": consts.LLM_ANALYSIS_FAILED(
                    result.get("error", "Unknown error")
                ),
            }
        try:
            final_analysis = self._parse_json_from_string(result["response"])
            if "job_classification_reasoning" in final_analysis:
                reasoning = final_analysis["job_classification_reasoning"]
                full_time_jobs = [
                    job
                    for job in reasoning
                    if not job.get("is_internship_or_training", False)
                ]
                final_analysis["total_jobs_count"] = len(full_time_jobs)
                final_analysis["fresher"] = len(full_time_jobs) == 0
                if final_analysis["fresher"]:
                    final_analysis["first_job_start_year"] = 0
                    final_analysis["last_job_end_year"] = 0
                else:
                    try:
                        start_years = []
                        end_years = []
                        for job in full_time_jobs:
                            sy = job.get("start_year")
                            ey = job.get("end_year")
                            if isinstance(sy, (int, float)):
                                start_years.append(int(sy))
                            if isinstance(ey, (int, float)):
                                end_years.append(int(ey))
                        if start_years:
                            final_analysis["first_job_start_year"] = min(start_years)
                        if end_years:
                            final_analysis["last_job_end_year"] = max(end_years)
                    except Exception as e:
                        logger.warning(
                            f"Failed to recalculate job years from reasoning: {e}"
                        )
                del final_analysis["job_classification_reasoning"]
            if "skill_reasoning" in final_analysis:
                del final_analysis["skill_reasoning"]
            elif final_analysis.get("fresher") is None:
                final_analysis["fresher"] = (
                    final_analysis.get("total_jobs_count", 0) == 0
                )
            final_analysis = self._enforce_resume_evidence(final_analysis, resume_text)
            validated_analysis = self._validate_analysis(final_analysis)
            return {
                "success": True,
                "analysis": validated_analysis,
                "processing_time": total_processing_time,
                "model_used": self.model_name,
                "error": None,
            }
        except Exception as e:
            logger.error(f"Error parsing single-pass LLM response: {e}")
            return {"success": False, "error": consts.PARSING_FAILED(e)}

    def _parse_json_from_string(self, text: str) -> Dict[str, Any]:
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start != -1 and json_end != -1:
            json_str = text[json_start:json_end]
            json_str = re.sub("//.*?(?=\\n|$)", "", json_str, flags=re.MULTILINE)
            json_str = re.sub(",(\\s*[}\\]])", "\\1", json_str)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing failed even after cleaning: {str(e)}")
                logger.error(f"Cleaned JSON string: {json_str[:500]}...")
                raise e
        else:
            raise json.JSONDecodeError(messages.JSON_OBJ_NOT_FOUND, text, 0)

    def _create_fallback_analysis(self, response: str) -> Dict[str, Any]:
        score_match = None
        score_patterns = [
            "score[:\\s]*(\\d+)",
            "rating[:\\s]*(\\d+)",
            "(\\d+)[/\\s]*100",
            "(\\d+)%",
        ]
        for pattern in score_patterns:
            match = re.search(pattern, response.lower())
            if match:
                try:
                    score_match = int(match.group(1))
                    break
                except:
                    continue
        fallback_score = min(max(score_match or 50, 0), 100)
        return {
            "candidate_name": messages.NAME_NOT_FOUND,
            "overall_score": fallback_score,
            "skills_match": fallback_score,
            "experience_relevance": fallback_score,
            "education": fallback_score,
            "keywords_match": fallback_score,
            "overall_fit": fallback_score,
            "matching_skills": [messages.UNABLE_TO_PARSE],
            "missing_skills": [messages.UNABLE_TO_PARSE],
            "matching_experience": [messages.UNABLE_TO_PARSE],
            "experience_gaps": [messages.UNABLE_TO_PARSE],
            "education_highlights": [messages.UNABLE_TO_PARSE],
            "strengths": [messages.ANALYSIS_PARSING_FAILED],
            "weaknesses": [messages.MANUAL_REVIEW_REQUIRED],
            "growth_potential": fallback_score,
            "cultural_fit_indicators": [messages.UNABLE_TO_ASSESS],
            "salary_expectation_alignment": "MEDIUM",
            "recommendation": "REJECT",
            "recommendation_reason": "Insufficient resume data",
            "summary": messages.ANALYSIS_COULD_NOT_BE_PARSED,
            "interview_focus_areas": [
                messages.TECHNICAL_ASSESSMENT,
                messages.EXPERIENCE_VERIFICATION,
            ],
        }

    def _enforce_resume_evidence(
        self, analysis: Dict[str, Any], resume_text: str
    ) -> Dict[str, Any]:
        resume_lower = (resume_text or "").lower()
        candidate_name = str(analysis.get("candidate_name") or "").strip()

        if candidate_name and candidate_name.lower() != messages.NAME_NOT_FOUND.lower():
            normalized_name = re.sub(r"\s+", " ", candidate_name).strip().lower()
            if normalized_name not in resume_lower:
                analysis["candidate_name"] = messages.NAME_NOT_FOUND

        # If resume has very little detail, force a conservative recommendation.
        if len(resume_text.split()) < 40:
            analysis["recommendation"] = "REJECT"
            analysis["recommendation_reason"] = "Insufficient resume data"

        return analysis

    def _validate_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        defaults = {
            "candidate_name": "Name not found",
            "overall_score": 50,
            "skills_match": 50,
            "experience_relevance": 50,
            "education": 50,
            "keywords_match": 50,
            "overall_fit": 50,
            "matching_skills": [],
            "missing_skills": [],
            "matching_experience": [],
            "experience_gaps": [],
            "education_highlights": [],
            "strengths": [],
            "weaknesses": [],
            "growth_potential": 50,
            "cultural_fit_indicators": [],
            "salary_expectation_alignment": "MEDIUM",
            "recommendation": "REJECT",
            "recommendation_reason": "Insufficient resume data",
            "summary": messages.ANALYSIS_COMPLETED,
            "interview_focus_areas": [],
            "fresher": True,
            "first_job_start_year": 0,
            "last_job_end_year": 0,
            "total_jobs_count": 0,
        }
        for key, default_value in defaults.items():
            analysis.setdefault(key, default_value)
        score_fields = [
            "overall_score",
            "skills_match",
            "experience_relevance",
            "education",
            "keywords_match",
            "overall_fit",
            "growth_potential",
        ]
        for field in score_fields:
            try:
                score = float(analysis[field])
                analysis[field] = max(0, min(100, score))
            except (ValueError, TypeError):
                analysis[field] = 50
        if analysis.get("recommendation") not in ["HIRE", "CONSIDER", "REJECT"]:
            analysis["recommendation"] = "CONSIDER"
        if analysis.get("salary_expectation_alignment") not in [
            "LOW",
            "MEDIUM",
            "HIGH",
        ]:
            analysis["salary_expectation_alignment"] = "MEDIUM"
        list_fields = [
            "matching_skills",
            "missing_skills",
            "matching_experience",
            "experience_gaps",
            "education_highlights",
            "strengths",
            "weaknesses",
            "cultural_fit_indicators",
            "interview_focus_areas",
        ]
        for field in list_fields:
            if not isinstance(analysis.get(field), list):
                analysis[field] = [str(analysis[field])] if analysis.get(field) else []
        return analysis

    def _validate_exact_structure(self, analysis: Dict[str, Any]) -> bool:
        required_llm_fields = [
            "candidate_name",
            "overall_score",
            "skills_match",
            "experience_relevance",
            "education",
            "keywords_match",
            "overall_fit",
            "matching_skills",
            "missing_skills",
            "matching_experience",
            "experience_gaps",
            "education_highlights",
            "strengths",
            "weaknesses",
            "growth_potential",
            "cultural_fit_indicators",
            "salary_expectation_alignment",
            "recommendation",
            "recommendation_reason",
            "summary",
            "interview_focus_areas",
            "matching_skills_count",
            "missing_skills_count",
            "relevant_experience_years",
            "education_level_code",
        ]
        allowed_extra_fields = [
            "fresher",
            "first_job_start_year",
            "last_job_end_year",
            "total_jobs_count",
            "job_classification_reasoning",
        ]
        missing_fields = [
            field for field in required_llm_fields if field not in analysis
        ]
        if missing_fields:
            logger.warning(f"LLM response missing required fields: {missing_fields}")
            return False
        all_allowed_fields = required_llm_fields + allowed_extra_fields
        extra_fields = [
            field for field in analysis.keys() if field not in all_allowed_fields
        ]
        if extra_fields:
            logger.warning(f"LLM response has unexpected extra fields: {extra_fields}")
            return False
        return True
