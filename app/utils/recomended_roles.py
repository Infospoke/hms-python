import json
import logging
from app.utils.groq_api import call_llm
from app.core import config as consts

logger = logging.getLogger(__name__)


MUST_HAVE_SKILLS_PROMPT = """You are a technical HR expert. Based on the job details below, suggest MUST-HAVE (essential) skills required for the role.

Job Title: {job_title}
Department: {department}
Business Case: {business_case}

Respond with a JSON array of skills in this exact format:
[
  {{"skill_title": "Skill Name", "skill_description": "Brief description (10-20 words)", "is_mandatory": true}},
  ...
]

Rules:
- Include ONLY essential skills without which the candidate cannot perform the job
- Return maximum 10 must-have skills (less is okay, but no more than 10)
- Include critical technical and soft skills
- Be concise and practical in descriptions
- Only include these fields: skill_title, skill_description
"""

NICE_TO_HAVE_SKILLS_PROMPT = """You are a technical HR expert. Based on the job details below, suggest NICE-TO-HAVE (optional) skills that would be beneficial for the role.

Job Title: {job_title}
Department: {department}
Business Case: {business_case}

Respond with a JSON array of skills in this exact format:
[
  {{"skill_title": "Skill Name", "skill_description": "Brief description (10-20 words)", "is_mandatory": false}},
  ...
]

Rules:
- Include ONLY beneficial skills that add value but are not required
- Return maximum 10 nice-to-have skills (less is okay, but no more than 10)
- Include nice-to-have technical skills and soft skills
- Be concise and practical in descriptions
- Only include these fields: skill_title, skill_description
"""

JOB_DESCRIPTION_PROMPT = """You are an expert HR professional and technical writer. Create a concise, professional job description (JD) in JSON format based on the details provided below.

IMPORTANT: Respond ONLY with valid JSON. No markdown code blocks, no explanations, just pure JSON.

SPEED & CONCISENESS RULES:
1. Keep the "job_summary" extremely brief and direct (exactly 1-2 short sentences).
2. Limit "key_responsibilities", "required_qualifications", and "preferred_qualifications" to at most 3 concise, high-impact bullet points each.
3. Keep the "about_company" section under 20 words.
4. Do not include any filler text or verbose sentences.

JOB DETAILS:
- Job Title: {job_title}
- Department: {department}
- Location: {location}
- Seniority Level: {seniority_level}
- Number of Openings: {num_openings}
- Target Start Date: {target_start_date}
- Employment Type: {employment_type}
- Work Mode: {work_mode}

ROLE REQUIREMENTS:
- Must-Have Skills: {must_have_skills}
- Nice-to-Have Skills: {nice_to_have_skills}
- Education Requirements: {education_requirements}
- Travel Requirement: {travel_requirement}
- Years of Experience: {years_of_experience}
- Required Certifications: {required_certifications}
- Languages: {languages}

Provide a professional job description JSON with these fields (fill in appropriate values based on the job details):
{{
  "job_title": "Job Title",
  "job_summary": "Brief overview of the role (1-2 sentences)",
  "key_responsibilities": ["Responsibility 1", "Responsibility 2", "Responsibility 3"],
  "basic_qualifications": ["Qualification 1", "Qualification 2", "Qualification 3"],
  "preferred_qualifications": ["Qualification 1", "Qualification 2"],
  "skills_must_have": ["Skill 1", "Skill 2", "Skill 3"],
  "skills_nice_to_have": ["Skill 1", "Skill 2"],
  "education_requirements": "Education requirement",
  "experience_requirements": "Experience requirement",
  "certifications_required": ["Certification 1", "Certification 2"],
  "languages_required": "English",
  "work_mode": "Work mode",
  "employment_type": "Employment type",
  "location": "Location",
}}

Respond with only the JSON object.
"""


class SkillGenerator:
    def __init__(self):
        pass

    async def generate_must_have_skills(
        self,
        job_title: str,
        department: str = "",
        business_case: str = "",
    ):
        prompt = MUST_HAVE_SKILLS_PROMPT.format(
            job_title=job_title or "Not specified",
            department=department or "Not provided",
            business_case=business_case or "Not provided",
        )

        try:
            result = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
            skills = []
            if isinstance(result, list):
                skills = result
            elif isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, list):
                        skills = v
                        break
            for skill in skills:
                skill["is_ai_suggested"] = True
                skill["is_mandatory"] = True
            return {"success": True, "skills": skills}
        except Exception as e:
            logger.error(f"Error generating must-have skills: {e}")
            return {"success": False, "error": str(e)}

    async def generate_nice_to_have_skills(
        self,
        job_title: str,
        department: str = "",
        business_case: str = "",
    ):
        prompt = NICE_TO_HAVE_SKILLS_PROMPT.format(
            job_title=job_title or "Not specified",
            department=department or "Not provided",
            business_case=business_case or "Not provided",
        )

        try:
            result = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
            skills = []
            if isinstance(result, list):
                skills = result
            elif isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, list):
                        skills = v
                        break
            for skill in skills:
                skill["is_ai_suggested"] = True
                skill["is_mandatory"] = False
            return {"success": True, "skills": skills}
        except Exception as e:
            logger.error(f"Error generating nice-to-have skills: {e}")
            return {"success": False, "error": str(e)}


REWRITE_JOB_DESCRIPTION_PROMPT = """You are an expert HR professional and technical writer. Create an optimized and rewritten job description (JD) in JSON format based on the old job description and the requested update instruction below.

CRITICAL INSTRUCTIONS:
1. You MUST use the content and facts provided in the Old Job Description as the primary source of truth.
2. Apply the requested update instruction with extreme precision, enhancing only the relevant sections to perfectly match the target parameter (e.g., seniority shift, conciseness, technical depth, or expanded duties).
3. Do NOT hallucinate, invent, or introduce false facts, company details, or unrealistic requirements.
4. Ensure the output is a professionally written, modern, and engaging job description.
5. Perform the rewrite specifically based on this instruction:
   {update_instruction}

OLD JOB DESCRIPTION:
{old_job_description}

IMPORTANT: Respond ONLY with valid JSON. No markdown code blocks, no explanations, just pure JSON in this exact format:
{{
  "job_title": "Optimized Job Title",
  "job_summary": "Comprehensive overview of the role (2-3 sentences)",
  "key_responsibilities": ["Enhanced Responsibility 1", "Enhanced Responsibility 2", "Enhanced Responsibility 3"],
  "basic_qualifications": ["Qualification 1", "Qualification 2", "Qualification 3"],
  "preferred_qualifications": ["Qualification 1", "Qualification 2"],
  "skills_must_have": ["Skill 1", "Skill 2", "Skill 3"],
  "skills_nice_to_have": ["Skill 1", "Skill 2"],
  "education_requirements": "Education requirement",
  "experience_requirements": "Experience requirement",
  "certifications_required": ["Certification 1", "Certification 2"],
  "languages_required": "English",
  "work_mode": "Work mode",
  "employment_type": "Employment type",
  "location": "Location"
}}
"""


class JobDescriptionGenerator:
    def __init__(self):
        pass

    async def generate_job_description(
        self,
        job_title: str,
        department: str = "",
        location: str = "",
        seniority_level: str = "",
        num_openings: int = 1,
        target_start_date: str = "",
        employment_type: str = "",
        work_mode: str = "",
        must_have_skills: list = None,
        nice_to_have_skills: list = None,
        education_requirements: str = "",
        travel_requirement: str = "",
        years_of_experience: str = "",
        required_certifications: list = None,
        languages: str = "",
    ):
        prompt = JOB_DESCRIPTION_PROMPT.format(
            job_title=job_title or "Not specified",
            department=department or "Not specified",
            location=location or "Not specified",
            seniority_level=seniority_level or "Not specified",
            num_openings=num_openings or 1,
            target_start_date=target_start_date or "Flexible",
            employment_type=employment_type or "Full-time",
            work_mode=work_mode or "Not specified",
            must_have_skills=", ".join(must_have_skills) if must_have_skills else "None specified",
            nice_to_have_skills=", ".join(nice_to_have_skills) if nice_to_have_skills else "None specified",
            education_requirements=education_requirements or "Not specified",
            travel_requirement=travel_requirement or "No travel required",
            years_of_experience=years_of_experience or "Not specified",
            required_certifications=", ".join(required_certifications) if required_certifications else "None required",
            languages=languages or "English",
        )

        try:
            result = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
            logger.info(f"JD generation response success, length: {len(str(result))}")
            logger.info(f"Parsed JD result: {result}")
            return {"success": True, "job_description": result}
        except Exception as e:
            logger.error(f"JD generation failed: {e}")
            return {"success": False, "error": str(e)}

    async def rewrite_job_description(
        self,
        old_job_description: str,
        update_parameter: str,
    ):
        instructions = {
            "rewrite for senior level": "Adjust the tone, expectations, and framing of tasks to reflect a senior professional (e.g., mentorship, leadership, higher ownership, strategic impact) without adding new technical skills or qualifications not present in the original description.",
            "rewrite for junior level": "Adjust the tone and expectations to reflect a junior/entry-level professional (e.g., support, learning, working under guidance, execution of tasks) without adding new qualifications.",
            "make concise": "Condense the information, remove redundancy, and make it shorter and more direct while preserving all essential details.",
            "make more technical": "Frame the responsibilities and skills in a more technical, professional, and precise language, highlighting the technical aspects of the tasks already described without inventing new skills or tools.",
            "expand responsibilities": "Elaborate on the existing responsibilities in the old job description, explaining them in more detail without adding entirely new or unrelated duties."
        }

        # Default fallback instruction if no exact match is found
        instruction = instructions.get(
            update_parameter.lower(),
            f"Rewrite the job description to align with: {update_parameter}"
        )

        prompt = REWRITE_JOB_DESCRIPTION_PROMPT.format(
            old_job_description=old_job_description,
            update_instruction=instruction,
        )

        try:
            result = await call_llm(prompt, model_name=consts.GROQ_MODEL_FOR_JOB_DESCRIPTION)
            logger.info(f"JD rewrite response success, length: {len(str(result))}")
            return {"success": True, "job_description": result}
        except Exception as e:
            logger.error(f"JD rewrite failed: {e}")
            return {"success": False, "error": str(e)}