import json
import logging
import asyncio
from app.utils.gemini_llm import call_llm

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

JOB_DESCRIPTION_PROMPT = """You are an expert HR professional and technical writer. Create a comprehensive job description (JD) in JSON format based on the details provided below.

IMPORTANT: Respond ONLY with valid JSON. No markdown code blocks, no explanations, just pure JSON.

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
  "job_summary": "Brief overview of the role (2-3 sentences)",
  "key_responsibilities": ["Responsibility 1", "Responsibility 2", "Responsibility 3"],
  "required_qualifications": ["Qualification 1", "Qualification 2", "Qualification 3"],
  "preferred_qualifications": ["Qualification 1", "Qualification 2"],
  "skills_must_have": ["Skill 1", "Skill 2", "Skill 3"],
  "skills_nice_to_have": ["Skill 1", "Skill 2"],
  "education_requirements": "Education requirement",
  "experience_requirements": "Experience requirement",
  "certifications_required": ["Certification 1"],
  "languages_required": "English",
  "travel_requirement": "Travel requirement",
  "work_mode": "Work mode",
  "employment_type": "Employment type",
  "location": "Location",
  "about_company": "Brief company description"
}}

Respond with only the JSON object.
"""


class SkillGenerator:
    def __init__(self):
        pass

    def generate_must_have_skills(
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
            result = asyncio.run(call_llm(prompt))
            skills = result if isinstance(result, list) else []
            for skill in skills:
                skill["is_ai_suggested"] = True
                skill["is_mandatory"] = True
            return {"success": True, "skills": skills}
        except Exception as e:
            logger.error(f"Error generating must-have skills: {e}")
            return {"success": False, "error": str(e)}

    def generate_nice_to_have_skills(
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
            result = asyncio.run(call_llm(prompt))
            skills = result if isinstance(result, list) else []
            for skill in skills:
                skill["is_ai_suggested"] = True
                skill["is_mandatory"] = False
            return {"success": True, "skills": skills}
        except Exception as e:
            logger.error(f"Error generating nice-to-have skills: {e}")
            return {"success": False, "error": str(e)}


class JobDescriptionGenerator:
    def __init__(self):
        pass

    def generate_job_description(
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
            result = asyncio.run(call_llm(prompt))
            logger.info(f"JD generation response success, length: {len(str(result))}")
            logger.info(f"Parsed JD result: {result}")
            return {"success": True, "job_description": result}
        except Exception as e:
            logger.error(f"JD generation failed: {e}")
            return {"success": False, "error": str(e)}