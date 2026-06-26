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

    def generate_custom_questions(self, count: int, difficulty: str, question_types: list) -> dict:
        prompt = f"""
You are an expert **Senior Interviewer**.
Your goal is to generate customized interview questions for the role of **{self.job_role}**.

**Interview Context:**
- Role: {self.job_role}
- Job Description (JD):
{self.job_description}

**Candidate Context:**
- Experience Level: {self.experience}
- Key Skills: {self.skills}
- Resume Summary: "{self.resume_text[:1500]}"

**Task:**
Generate exactly {count} interview questions.
- Difficulty Level: {difficulty}
- Allowed Question Types: {", ".join(question_types)}

Each question must be tailored to the candidate's background and the job description.

**VARIETY, UNIQUENESS & DIVERSITY (CRITICAL):**
- Ensure all questions are **highly unique, distinct, and creative**.
- Do not repeat the same question or ask similar questions across different types.
- EVERY single question must be completely different. DO NOT repeat the same query or sentence structure.
- AVOID generic or textbook questions.
- Every time this generator runs, it must produce a completely different set of questions.
- Context ID: {uuid.uuid4()}

**CRITICAL GUIDELINES - QUESTION STRUCTURE:**
1. **SINGLE QUESTION CONSTRAINT:** Each generated question MUST contain exactly ONE question mark. Keep the wording punchy and concise (maximum 20-30 words).
2. **TTS-Friendly Formatting:** Avoid parentheses, brackets, or abbreviations (e.g., use "for example" instead of "e.g.").
3. **Conversational Tone:** Avoid textbook definition questions. Ask how they applied a skill or would handle a scenario.

**Output Format:**
Return a raw JSON object containing the total questions count and the list of question details. You must strictly adhere to the following JSON structure and return ONLY valid JSON:
{{
    "total_questions": {count},
    "questions": [
        {{
            "question_id": 1,
            "question": "The actual question text here...",
            "expected_time": "2-3 mins",
            "difficulty_level": "{difficulty.lower()}",
            "question_type": "one of the allowed question types"
        }}
    ]
}}
"""
        try:
            logger.info(f"Generating custom questions: count={count}, difficulty={difficulty}, types={question_types}")
            result = self.generate_response(prompt)
            if result.get("success"):
                response_text = result["response"]
                parsed = self.parse_json(response_text)
                if isinstance(parsed, list):
                    parsed = {
                        "total_questions": len(parsed),
                        "questions": parsed
                    }
                if isinstance(parsed, dict) and "questions" in parsed:
                    cleaned_questions = []
                    for idx, q in enumerate(parsed["questions"]):
                        q_id = q.get("question_id") or (idx + 1)
                        q_text = q.get("question") or q.get("question_text") or ""
                        q_time = q.get("expected_time") or "2-3 mins"
                        
                        # Handle potential AI mix-up of question_type and difficulty_level
                        q_diff = str(q.get("difficulty_level") or "").lower()
                        q_type = str(q.get("question_type") or "").lower()
                        
                        valid_types = ["technical", "situational", "behavioural", "behavioral"]
                        
                        # If question_type is missing or invalid, but difficulty_level has a valid type name:
                        if (not q_type or q_type not in valid_types) and q_diff in valid_types:
                            q_type = q_diff
                            q_diff = difficulty.lower()
                            
                        # Standard fallbacks if still missing
                        if not q_type or q_type not in valid_types:
                            q_type = question_types[idx % len(question_types)] if question_types else "technical"
                            
                        if not q_diff:
                            q_diff = difficulty.lower()
                            
                        cleaned_questions.append({
                            "question_id": q_id,
                            "question": q_text,
                            "expected_time": q_time,
                            "difficulty_level": q_diff,
                            "question_type": q_type
                        })
                    
                    parsed["questions"] = cleaned_questions[:count]
                    parsed["total_questions"] = len(parsed["questions"])
                    return parsed
        except Exception as e:
            logger.error(f"Error in generate_custom_questions with Gemini: {e}")
            logger.info("Attempting fallback to Groq...")
            try:
                from groq import Groq
                if consts.GROQ_API_KEY:
                    groq_client = Groq(api_key=consts.GROQ_API_KEY)
                    groq_model = consts.GROQ_MODEL or "llama-3.3-70b-versatile"
                    
                    chat_completion = groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=groq_model,
                        temperature=0.7,
                        response_format={"type": "json_object"}
                    )
                    raw_resp = chat_completion.choices[0].message.content.strip()
                    parsed = self.parse_json(raw_resp)
                    if isinstance(parsed, list):
                        parsed = {
                            "total_questions": len(parsed),
                            "questions": parsed
                        }
                    if isinstance(parsed, dict) and "questions" in parsed:
                        cleaned_questions = []
                        for idx, q in enumerate(parsed["questions"]):
                            q_id = q.get("question_id") or (idx + 1)
                            q_text = q.get("question") or q.get("question_text") or ""
                            q_time = q.get("expected_time") or "2-3 mins"
                            
                            q_diff = str(q.get("difficulty_level") or "").lower()
                            q_type = str(q.get("question_type") or "").lower()
                            
                            valid_types = ["technical", "situational", "behavioural", "behavioral"]
                            if (not q_type or q_type not in valid_types) and q_diff in valid_types:
                                q_type = q_diff
                                q_diff = difficulty.lower()
                                
                            if not q_type or q_type not in valid_types:
                                q_type = question_types[idx % len(question_types)] if question_types else "technical"
                                
                            if not q_diff:
                                q_diff = difficulty.lower()
                                
                            cleaned_questions.append({
                                "question_id": q_id,
                                "question": q_text,
                                "expected_time": q_time,
                                "difficulty_level": q_diff,
                                "question_type": q_type
                            })
                        parsed["questions"] = cleaned_questions[:count]
                        parsed["total_questions"] = len(parsed["questions"])
                        logger.info("Successfully generated custom questions using Groq fallback.")
                        return parsed
            except Exception as groq_err:
                logger.error(f"Groq fallback failed: {groq_err}")

        logger.error("Both Gemini and Groq custom question generation failed. Returning empty list.")
        return {
            "total_questions": 0,
            "questions": []
        }

