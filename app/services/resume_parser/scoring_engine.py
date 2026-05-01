import logging
import re
from typing import Dict, List, Any
from datetime import datetime
from .client import Client
import app.core.config as consts
from app.core import messages
from collections import Counter
from app.utils import timezone_utils

# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- SCORING ENGINE ---


class ScoringEngine:

    def __init__(self):
        self.client = Client()
        self.weights = consts.SCORING_WEIGHTS
        self.max_score = consts.MAX_SCORE
        self.min_score = consts.MIN_SCORE
        self.passing_score = consts.PASSING_SCORE

    def estimate_cost(self, resume_text: str, job_description: str) -> int:
        user_prompt = consts.USER_PROMPT(job_description, resume_text)
        main_system_prompt = consts.MAIN_SYSTEM_PROMPT
        full_text = main_system_prompt + "\n" + user_prompt
        return self.client.get_token_count(full_text)

    def score_resume(
        self, resume_data: Dict[str, Any], job_description: str
    ) -> Dict[str, Any]:
        if not resume_data.get("success", False):
            return {
                "success": False,
                "error": resume_data.get("error", messages.RESUME_PARSING_FAILED),
                "filename": resume_data.get("filename", "unknown"),
                "scores": {},
                "recommendation": "REJECT",
            }
        try:
            resume_text = (resume_data.get("text") or "").strip()
            word_count = resume_data.get("metadata", {}).get("word_count", 0)
            if not resume_text or word_count < 20:
                return self._build_insufficient_resume_result(resume_data)
            llm_result = self.client.analyze_resume(
                resume_text, job_description
            )
            if not llm_result["success"]:
                logger.error(f"LLM analysis failed: {llm_result['error']}")
                return {
                    "success": False,
                    "error": f"LLM analysis failed: {llm_result['error']}",
                    "filename": resume_data["filename"],
                    "scores": {},
                    "recommendation": "REJECT",
                }
            analysis = llm_result["analysis"]
            matching = analysis.get("matching_skills", [])
            missing = analysis.get("missing_skills", [])
            required_count = len(matching) + len(missing)
            analysis["required_skills_count"] = required_count
            analysis["matched_skills_count"] = len(matching)
            if required_count > 0:
                coverage = len(matching) / required_count * 100
                analysis["skills_coverage_percentage"] = coverage
                analysis["meets_minimum_skills"] = (
                    coverage >= consts.MINIMUM_SKILLS_PERCENTAGE
                )
                analysis["skills_match"] = coverage
            else:
                analysis["skills_coverage_percentage"] = 0
                analysis["meets_minimum_skills"] = False
                analysis["skills_match"] = 0
            combined_scores = self._combine_scores(
                analysis, resume_data, job_description
            )
            final_score, recommendation = self._calculate_skills_first_score(
                combined_scores
            )
            llm_name = analysis.get("candidate_name", "")
            parser_name = resume_data.get("metadata", {}).get(
                "candidate_name", "Name not found"
            )
            best_name = (
                llm_name
                if llm_name
                and llm_name != "Name not found"
                and len(llm_name.split()) >= 2
                else parser_name
            )
            updated_metadata = resume_data.get("metadata", {}).copy()
            updated_metadata["candidate_name"] = best_name
            result = {
                "success": True,
                "filename": resume_data["filename"],
                "final_score": round(final_score, 2),
                "scores": combined_scores,
                "recommendation": recommendation,
                "analysis": analysis,
                "strengths": analysis.get("strengths", []),
                "weaknesses": analysis.get("weaknesses", []),
                "summary": analysis.get("summary", ""),
                "processing_time": llm_result.get("processing_time", 0),
                "metadata": updated_metadata,
                "timestamp": timezone_utils.format_datetime_for_api(
                    timezone_utils.get_ist_now()
                ),
            }
            return result
        except Exception as e:
            logger.error(
                f"Error scoring resume {resume_data.get('filename', 'unknown')}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "filename": resume_data.get("filename", "unknown"),
                "scores": {},
                "recommendation": "REJECT",
            }

    def _build_insufficient_resume_result(
        self, resume_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        metadata = resume_data.get("metadata", {}).copy()
        metadata["candidate_name"] = messages.NAME_NOT_FOUND
        analysis = {
            "candidate_name": messages.NAME_NOT_FOUND,
            "overall_score": 0,
            "skills_match": 0,
            "experience_relevance": 0,
            "education": 0,
            "keywords_match": 0,
            "overall_fit": 0,
            "matching_skills": [],
            "missing_skills": [],
            "matching_experience": [],
            "experience_gaps": [],
            "education_highlights": [],
            "matching_education": [],
            "missing_education": [],
            "strengths": [],
            "weaknesses": [
                "Resume content is empty or too short for analysis"
            ],
            "growth_potential": 0,
            "cultural_fit_indicators": [],
            "salary_expectation_alignment": "LOW",
            "recommendation": "REJECT",
            "recommendation_reason": "Insufficient resume data",
            "summary": "Resume has insufficient textual content. Please upload a text-based resume.",
            "interview_focus_areas": [],
            "fresher": True,
            "first_job_start_year": 0,
            "last_job_end_year": 0,
            "total_jobs_count": 0,
        }
        scores = {
            "skills_match": 0,
            "experience_relevance": 0,
            "education": 0,
            "keywords_match": 0,
            "overall_fit": 0,
        }
        return {
            "success": True,
            "filename": resume_data.get("filename", "unknown"),
            "final_score": 0,
            "scores": scores,
            "recommendation": "REJECT",
            "analysis": analysis,
            "strengths": [],
            "weaknesses": analysis["weaknesses"],
            "summary": analysis["summary"],
            "processing_time": 0,
            "metadata": metadata,
            "timestamp": timezone_utils.format_datetime_for_api(
                timezone_utils.get_ist_now()
            ),
        }

    def _combine_scores(
        self,
        llm_analysis: Dict[str, Any],
        resume_data: Dict[str, Any],
        job_description: str,
    ) -> Dict[str, float]:
        combined_scores = {
            "skills_match": llm_analysis.get("skills_match", 50),
            "experience_relevance": llm_analysis.get("experience_relevance", 50),
            "education": llm_analysis.get("education", 50),
            "keywords_match": llm_analysis.get("keywords_match", 50),
            "overall_fit": llm_analysis.get("overall_fit", 50),
        }
        adjustments = self._calculate_rule_based_adjustments(
            resume_data, job_description
        )
        for criterion, base_score in combined_scores.items():
            adjustment = adjustments.get(criterion, 0)
            adjusted_score = base_score + adjustment
            combined_scores[criterion] = max(
                self.min_score, min(self.max_score, adjusted_score)
            )
        return combined_scores

    def _calculate_rule_based_adjustments(
        self, resume_data: Dict[str, Any], job_description: str
    ) -> Dict[str, float]:
        adjustments = {
            "skills_match": 0,
            "experience_relevance": 0,
            "education": 0,
            "keywords_match": 0,
            "overall_fit": 0,
        }
        resume_text = resume_data.get("text", "").lower()
        job_desc_lower = job_description.lower()
        metadata = resume_data.get("metadata", {})
        job_keywords = self._extract_keywords(job_desc_lower)
        keyword_matches = sum(1 for keyword in job_keywords if keyword in resume_text)
        if job_keywords:
            keyword_match_ratio = keyword_matches / len(job_keywords)
            adjustments["keywords_match"] += (keyword_match_ratio - 0.5) * 20
        if metadata.get("has_email") and metadata.get("has_phone"):
            adjustments["overall_fit"] += 5
        if metadata.get("has_linkedin"):
            adjustments["overall_fit"] += 3
        if metadata.get("has_github"):
            adjustments["skills_match"] += 5
        word_count = metadata.get("word_count", 0)
        if word_count < 100:
            adjustments["overall_fit"] -= 10
        elif word_count > 2000:
            adjustments["overall_fit"] -= 5
        experience_indicators = [
            "years",
            "experience",
            "worked",
            "developed",
            "managed",
            "led",
        ]
        experience_count = sum(
            1 for indicator in experience_indicators if indicator in resume_text
        )
        if experience_count >= 3:
            adjustments["experience_relevance"] += 5
        education_adjustments = 0
        if any(
            keyword in resume_text
            for keyword in ["phd", "ph.d", "doctorate", "doctoral"]
        ):
            education_adjustments = 40
        elif any(
            keyword in resume_text
            for keyword in [
                "master",
                "msc",
                "m.sc",
                "mba",
                "m.b.a",
                "mtech",
                "m.tech",
                "postgraduate",
            ]
        ):
            education_adjustments = 25
        elif any(
            keyword in resume_text
            for keyword in [
                "bachelor",
                "bsc",
                "b.sc",
                "btech",
                "b.tech",
                "be",
                "b.e",
                "undergraduate",
            ]
        ):
            education_adjustments = 15
        elif any(
            keyword in resume_text
            for keyword in ["diploma", "associate", "polytechnic"]
        ):
            education_adjustments = 5
        elif any(
            keyword in resume_text
            for keyword in ["high school", "secondary", "12th", "intermediate"]
        ):
            education_adjustments = -10
        adjustments["education"] += education_adjustments
        return adjustments

    def _extract_keywords(self, text: str) -> List[str]:
        text = text.lower()
        text = re.sub("[^a-z0-9\\s]", "", text)
        stopwords = set(
            [
                "a",
                "an",
                "the",
                "and",
                "or",
                "but",
                "if",
                "then",
                "else",
                "when",
                "at",
                "from",
                "by",
                "on",
                "off",
                "for",
                "in",
                "out",
                "over",
                "to",
                "into",
                "with",
                "about",
                "against",
                "between",
                "through",
                "during",
                "before",
                "after",
                "above",
                "below",
                "up",
                "down",
                "under",
                "again",
                "further",
                "once",
                "here",
                "there",
                "where",
                "why",
                "how",
                "all",
                "any",
                "both",
                "each",
                "few",
                "more",
                "most",
                "other",
                "some",
                "such",
                "no",
                "nor",
                "not",
                "only",
                "own",
                "same",
                "so",
                "than",
                "too",
                "very",
                "can",
                "will",
                "just",
                "should",
                "now",
                "are",
                "is",
                "was",
                "were",
                "be",
                "been",
                "being",
                "have",
                "has",
                "had",
                "having",
                "do",
                "does",
                "did",
                "doing",
                "i",
                "me",
                "my",
                "myself",
                "we",
                "our",
                "ours",
                "ourselves",
                "you",
                "your",
                "yours",
                "yourself",
                "yourselves",
                "he",
                "him",
                "his",
                "himself",
                "she",
                "her",
                "hers",
                "herself",
                "it",
                "its",
                "itself",
                "they",
                "them",
                "their",
                "theirs",
                "themselves",
                "what",
                "which",
                "who",
                "whom",
                "this",
                "that",
                "these",
                "those",
                "experience",
                "year",
                "years",
                "work",
                "working",
                "job",
                "role",
                "candidate",
                "team",
                "company",
                "client",
                "project",
                "looking",
                "seeking",
                "opportunity",
                "skills",
                "knowledge",
                "abilities",
                "responsibilities",
                "duties",
                "requirements",
                "qualifications",
                "preferred",
                "plus",
                "like",
                "good",
                "strong",
                "excellent",
                "proven",
                "track",
                "record",
                "ability",
                "proficient",
                "proficiency",
                "familiarity",
                "ensure",
                "help",
                "support",
                "using",
                "used",
                "make",
                "made",
                "build",
                "built",
                "create",
                "created",
                "develop",
                "developed",
                "maintain",
                "maintained",
                "manage",
                "managed",
                "lead",
                "led",
                "participate",
                "participated",
                "contribute",
                "contributed",
                "join",
                "ideal",
                "services",
                "environment",
                "essential",
            ]
        )
        words = text.split()
        filtered_words = [
            word
            for word in words
            if word not in stopwords and len(word) > 1 and not word.isdigit()
        ]
        ngrams = []
        ngrams.extend(filtered_words)
        for i in range(len(filtered_words) - 1):
            ngrams.append(f"{filtered_words[i]} {filtered_words[i + 1]}")
        for i in range(len(filtered_words) - 2):
            ngrams.append(
                f"{filtered_words[i]} {filtered_words[i + 1]} {filtered_words[i + 2]}"
            )
        ngram_counts = Counter(ngrams)
        final_keywords = set()
        common_keywords_list = consts.COMMON_KEYWORDS
        for ck in common_keywords_list:
            if ck.lower() in text:
                final_keywords.add(ck.lower())
        most_common = ngram_counts.most_common(20)
        for ngram, count in most_common:
            final_keywords.add(ngram)
        return list(final_keywords)

    def _calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        weighted_sum = 0
        total_weight = 0
        for criterion, score in scores.items():
            weight = self.weights.get(criterion, 0)
            weighted_sum += score * weight
            total_weight += weight
        if total_weight == 0:
            return 50
        return weighted_sum / total_weight

    def _generate_recommendation(
        self, final_score: float, scores: Dict[str, float]
    ) -> str:
        if final_score >= 80:
            return "HIRE"
        elif final_score >= self.passing_score:
            critical_areas = ["skills_match", "experience_relevance"]
            critical_scores = [scores.get(area, 0) for area in critical_areas]
            if any(score < 40 for score in critical_scores):
                return "CONSIDER"
            else:
                return "HIRE"
        elif final_score >= 40:
            return "CONSIDER"
        else:
            return "REJECT"

    def _calculate_skills_first_score(self, scores: Dict[str, float]) -> tuple:
        skills_score = scores.get("skills_match", 0)
        experience_score = scores.get("experience_relevance", 0)
        if skills_score < consts.SKILLS_VETO_THRESHOLD:
            return 0, "REJECT"
        if skills_score >= consts.CRITICAL_SKILLS_THRESHOLD:
            final_score = self._calculate_weighted_score(scores)
        elif skills_score >= consts.MINIMUM_SKILLS_PERCENTAGE:
            base_score = self._calculate_weighted_score(scores)
            if experience_score > 80 and skills_score < 50:
                experience_penalty = (80 - skills_score) * 0.5
                final_score = max(base_score - experience_penalty, skills_score)
            else:
                final_score = base_score
        else:
            final_score = skills_score * 0.8
        final_score = max(0, min(100, final_score))
        recommendation = self._generate_skills_based_recommendation(
            final_score, skills_score, scores
        )
        return round(final_score, 2), recommendation

    def _generate_skills_based_recommendation(
        self, final_score: float, skills_score: float, scores: Dict[str, float]
    ) -> str:
        experience_score = scores.get("experience_relevance", 0)
        scores.get("education", 0)
        if skills_score < consts.SKILLS_VETO_THRESHOLD:
            return "REJECT"
        if skills_score >= 80:
            if final_score >= 85:
                return "HIRE"
            elif final_score >= 70:
                return "HIRE" if experience_score >= 60 else "CONSIDER"
            else:
                return "CONSIDER"
        elif skills_score >= consts.CRITICAL_SKILLS_THRESHOLD:
            if final_score >= 80 and experience_score >= 70:
                return "HIRE"
            elif final_score >= 70:
                return "CONSIDER"
            else:
                return "REJECT"
        elif skills_score >= consts.MINIMUM_SKILLS_PERCENTAGE:
            if final_score >= 75 and experience_score >= 85:
                return "CONSIDER"
            else:
                return "REJECT"
        else:
            return "REJECT"
