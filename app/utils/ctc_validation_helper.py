import re
import json
import httpx
from fastapi import HTTPException
from typing import Optional
from app.schemas import (
    SalaryBenchmark,
    CTCReviewRequest,
    SeniorityLevel,
)
from app.core.config import RAPIDAPI_KEY, SALARY_API_HOST
from app.core import config as consts


JOB_SALARY_DATA_YEARS_OF_EXPERIENCE = {
    SeniorityLevel.IC1: "LESS_THAN_ONE",
    SeniorityLevel.IC2: "ONE_TO_THREE",
    SeniorityLevel.IC3: "FOUR_TO_SIX",
    SeniorityLevel.IC4: "SEVEN_TO_NINE",
    SeniorityLevel.IC5: "TEN_TO_FOURTEEN",
    SeniorityLevel.IC6: "ABOVE_FIFTEEN",
    SeniorityLevel.IC7: "ABOVE_FIFTEEN",
    SeniorityLevel.M1: "SEVEN_TO_NINE",
    SeniorityLevel.M2: "TEN_TO_FOURTEEN",
    SeniorityLevel.M3: "ABOVE_FIFTEEN",
    SeniorityLevel.M4: "ABOVE_FIFTEEN",
    SeniorityLevel.M5: "ABOVE_FIFTEEN",
}


def parse_ctc_to_lpa(ctc_str: str) -> Optional[float]:
    ctc_str = ctc_str.replace(",", "").strip()
    match = re.search(r"[\d.]+", ctc_str)
    if not match:
        return None
    value = float(match.group())
    if value > 1000:
        value = value / 100_000
    return value


async def fetch_salary_benchmarks(
    job_title: str,
    location: str,
    employment_type: str,
    seniority: SeniorityLevel,
) -> list[SalaryBenchmark]:
    if not RAPIDAPI_KEY:
        raise HTTPException(
            status_code=500,
            detail="RAPIDAPI_KEY is not configured.",
        )

    benchmarks: list[SalaryBenchmark] = []

    # Job Salary Data API
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://job-salary-data.p.rapidapi.com/job-salary",
                params={
                    "job_title": job_title,
                    "location": f"{location}, India" if "india" not in location.lower() else location,
                    "radius": "100",
                    "years_of_experience": JOB_SALARY_DATA_YEARS_OF_EXPERIENCE.get(
                        seniority, "ALL"
                    ),
                },
                headers={
                    "X-RapidAPI-Key": RAPIDAPI_KEY,
                    "X-RapidAPI-Host": SALARY_API_HOST,
                },
            )
        data = resp.json()
        print(f"[SalaryDataAPI] Response status: {resp.status_code}, data: {data}")
        if data.get("status") == "OK" and data.get("data"):
            for item in data["data"]:
                benchmarks.append(
                    SalaryBenchmark(
                        source=item.get("publisher_name", "Job Salary Data"),
                        min_salary=item.get("min_salary"),
                        max_salary=item.get("max_salary"),
                        median_salary=item.get("median_salary"),
                        currency=item.get("salary_currency", "INR"),
                        period=item.get("salary_period", "YEAR"),
                    )
                )
    except Exception as e:
        print(f"[SalaryDataAPI] Error: {e}")

    return benchmarks


def build_benchmark_summary(
    benchmarks: list[SalaryBenchmark], proposed_lpa: Optional[float]
) -> str:
    if not benchmarks:
        return "No live market salary data could be retrieved."

    lines = []
    for b in benchmarks:
        # Normalise to annual INR LPA
        min_v = b.min_salary
        max_v = b.max_salary
        med_v = b.median_salary

        # Convert monthly -> annual
        if b.period and "MONTH" in b.period.upper():
            min_v = (min_v or 0) * 12
            max_v = (max_v or 0) * 12
            med_v = (med_v or 0) * 12

        # Convert USD -> INR (rough: 1 USD ≈ 83 INR)
        if b.currency and b.currency.upper() == "USD":
            min_v = (min_v or 0) * 83
            max_v = (max_v or 0) * 83
            med_v = (med_v or 0) * 83

        # Convert absolute INR -> LPA
        def to_lpa(v):
            if v and v > 1000:
                return round(v / 100_000, 2)
            return v

        line = (
            f"  • {b.source}: "
            f"Min ₹{to_lpa(min_v)} LPA | "
            f"Median ₹{to_lpa(med_v)} LPA | "
            f"Max ₹{to_lpa(max_v)} LPA"
        )
        lines.append(line)

    summary = "Live market salary benchmarks (annual, INR):\n" + "\n".join(lines)
    if proposed_lpa:
        summary += f"\n\nProposed CTC: ₹{proposed_lpa} LPA"
    return summary


def build_llm_prompt(req: CTCReviewRequest, benchmark_text: str) -> Optional[str]:
    if not benchmark_text:
        return None

    return f"""You are a senior HR compensation analyst specialising in the Indian tech job market.

You are reviewing a Staffing Request (SR) for a new hire. Your task is to evaluate the **Proposed CTC** against current market benchmarks and contextual factors, then assign a rating.

---
## Staffing Request Details

- **Job Title:** {req.job_title}
- **Department:** {req.department}
- **Seniority:** {req.seniority.value}
- **Location:** {req.location} (Onsite)
- **Employment Type:** {req.employment_type}
- **Business Justification:** {req.business_justification}
- **Proposed CTC:** {req.proposed_ctc}

---
## Market Salary Data

{benchmark_text}

---
## Rating Criteria

Assign one of the following ratings:

| Rating | Meaning |
|--------|---------|
| **Green** | Proposed CTC is competitive and within/above the market median. Likely to attract and retain top talent. |
| **Yellow** | Proposed CTC is slightly below market median (within ~15% gap) OR data is limited. Acceptable but may slow hiring or lead to early attrition. |
| **Red** | Proposed CTC is significantly below market (>15% gap from median) or clearly uncompetitive for the seniority/location. High risk of offer rejection or attrition. |

---
## Instructions

1. Compare the proposed CTC to the market benchmarks.
2. Factor in: seniority level, location (Hyderabad tier-1 tech hub), employment type, and business urgency from the justification.
3. Provide a clear, concise justification (3-5 sentences max).
4. Return your response as **valid JSON only**, no markdown, no extra text:

{{
  "rating": "Green" | "Yellow" | "Red",
  "justification": "...",
  "summary": "One-line headline of your assessment"
}}
"""