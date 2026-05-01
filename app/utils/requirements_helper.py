from app.schemas import JobRequirementsRequest


def build_certifications_prompt(req: JobRequirementsRequest) -> str:
    return f"""You are an expert technical recruiter and HR specialist.

Based on the following job requirements, suggest the most relevant professional certifications that a candidate should possess.

### Job Details
- Job Title: {req.job_title}
- Department: {req.department}
- Seniority: {req.seniority.value}
- Business Justification: {req.business_justification}

Provide a list of maximum 10 certifications (less is okay). Just include the certification name.

Return your response as **valid JSON only**, no markdown, no extra text:

{{
  "certifications": [
    {{
      "name": "..."
    }}
  ]
}}
"""


def build_languages_prompt(req: JobRequirementsRequest) -> str:
    return f"""You are an expert technical recruiter and HR specialist.

Based on the following job requirements and location, suggest the required speaking (human) languages that a candidate must be proficient in. 
You must and should always include "English" as one of the required languages.

### Job Details
- Job Title: {req.job_title}
- Department: {req.department}
- Location: {req.location}
- Seniority: {req.seniority.value}
- Business Justification: {req.business_justification}

Provide a list of maximum 5 languages (less is okay). You must always include "English".

Return your response as **valid JSON only**, no markdown, no extra text:

{{
  "languages": [
    {{
      "language": "..."
    }}
  ],
  "summary": "One-line summary of the language requirements"
}}
"""


def build_qualifications_prompt(req: JobRequirementsRequest) -> str:
    return f"""You are an expert technical recruiter and HR specialist.

Based on the job details provided, suggest the most relevant educational qualifications that a candidate should possess.

### Job Details
- Job Title: {req.job_title}
- Department: {req.department}
- Location: {req.location}
- Seniority Level: {req.seniority.value}
- Business Justification: {req.business_justification}

Generate degree based on job_title, department, location, seniority, and business_justification. Use clear degree names like "B.Tech", "M.Tech", "Bachelor of Technology", "Master of Technology", "PhD", "MCA", "BCA", "MBA", etc.

Return your response as **valid JSON only**, no markdown, no extra text:

{{
  "qualifications": [
    {{
      "degree": "..."
    }}
  ]
}}
"""
