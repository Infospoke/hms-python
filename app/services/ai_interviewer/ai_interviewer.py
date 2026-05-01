import json
import logging
import uuid
import random
from app.core import config as consts
from app.services.resume_parser.gemini_client import GeminiClient
from .prompts import INTERVIEW_GENERATION_PROMPT, INTERVIEW_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)

# --- BASE INTERVIEWER CLASS ---


class BaseInterviewer(GeminiClient):

    def __init__(
        self,
        job_role,
        job_description,
        experience,
        max_questions=None,
        skills="",
        topics=[""],
        resume_text="",
    ):
        super().__init__(model=consts.GEMINI_MODEL_FOR_AI_INTERVIEWER)
        self.job_role = job_role
        self.job_description = job_description
        self.experience = experience

        self.max_questions = (
            max_questions if max_questions is not None else consts.MAX_QUESTIONS or 5
        )

        self.skills = skills
        self.topics = topics
        self.resume_text = resume_text or "No resume text provided."

    def parse_json(self, text):
        try:
            clean_text = text.replace("```json", "").replace("```", "").strip()
            start_idx = (
                clean_text.find("[")
                if clean_text.find("[") != -1
                else clean_text.find("{")
            )
            end_idx = (
                clean_text.rfind("]")
                if clean_text.rfind("]") != -1
                else clean_text.rfind("}")
            )
            if start_idx != -1 and end_idx != -1:
                clean_text = clean_text[start_idx : end_idx + 1]
            return json.loads(clean_text)
        except Exception as e:
            logger.error(f"JSON parsing error: {e}")
            return None


INTERVIEW_FOCUS_AREAS = [
    "Practical Application & Use Cases",
    "Problem Solving & Troubleshooting",
    "Strategy & Planning",
    "Process Optimization",
    "Best Practices & Standards",
    "Trade-offs & Decision Making",
    "Quality & Maintainability",
    "Collaboration & Team Dynamics",
    "Adaptability & Continuous Learning",
    "Project & Time Management",
]


# --- AI INTERVIEWER IMPLEMENTATION ---


class AIInterviewer(BaseInterviewer):

    def generate_questions(self):
        if len(self.topics) >= 3:
            selected_topics = ", ".join(random.sample(self.topics, 3))
        else:
            selected_topics = ", ".join(self.topics)
        focus_area = random.choice(INTERVIEW_FOCUS_AREAS)
        logger.info(
            f"Generating questions - Topics: {selected_topics}, Theme: {focus_area}"
        )
        prompt = INTERVIEW_GENERATION_PROMPT.format(
            role=self.job_role,
            job_description=self.job_description,
            experience=self.experience,
            skills=self.skills,
            resume_excerpt=self.resume_text[:1500],
            count=self.max_questions,
            technical_count = self.max_questions//2 if self.max_questions%2 == 0 else (self.max_questions//2 + 1),
            behavioral_count = self.max_questions//2,
            topics=selected_topics,
            # focus_area=focus_area,
        )
        prompt += f"""
        

(Context ID: {uuid.uuid4()})
        Ensure questions are **unique** and **distinct** from previous sessions.
        AVOID generic questions.
        """

        try:
            logger.debug(f"Question generation focused on: {selected_topics}")

            result = self.generate_response(prompt)
            if result.get("success"):
                response_text = result["response"]
                questions = self.parse_json(response_text)

                if isinstance(questions, list):
                    return questions[: self.max_questions*2]

            return ["Describe a challenging technical problem you solved."]
        except Exception as e:
            logger.error(f"Error generating technical questions: {e}")
            return ["Tell me about your experience with this role."]

    def analyze_answer(self, question, answer):
        prompt = INTERVIEW_ANALYSIS_PROMPT.format(
            role=self.job_role, question=question, answer=answer
        )
        try:
            result = self.generate_response(prompt)
            if result.get("success"):
                response_text = result["response"]
                data = self.parse_json(response_text)

                if data:
                    overall = (
                        data.get("domain_knowledge", 0)
                        + data.get("problem_solving", 0)
                        + data.get("job_relevance", 0)
                        + data.get("communication_clarity", 0)
                    ) / 4.0
                    data["overall"] = round(overall * 10, 1)
                    return data
        except Exception as e:
            logger.error(f"Error analyzing interview answer: {e}")
        return {
            "overall": 0,
            "feedback": "Error analyzing response.",
            "domain_knowledge": 0,
        }
