from datetime import datetime
from typing import Any, Optional
from fastapi import Request
from app.utils import timezone_utils
import secrets
import string



def construct_job_description_for_llm(
    job_title, job_info, job_description, job_requirements, qualification, skills
):
    parts = []
    if job_title:
        parts.append(f"Job Title: {job_title}")
    if job_info:
        parts.append(f"Job Info: {job_info}")
    if job_description:
        parts.append(f"Description: {job_description}")
    if job_requirements:
        parts.append(f"Requirements: {job_requirements}")
    if qualification:
        parts.append(f"Qualifications: {qualification}")
    if skills:
        parts.append(f"Skills: {skills}")
    return "\n\n".join(parts) if parts else ""


def format_datetime_response(data: Any) -> Any:
    if isinstance(data, datetime):
        return timezone_utils.format_datetime_for_api(data)
    elif isinstance(data, dict):
        return {key: format_datetime_response(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [format_datetime_response(item) for item in data]
    else:
        return data

def generate_quit_password(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def _wants_html(request: Request) -> bool:
    accept_header = request.headers.get("accept", "")
    return "text/html" in accept_header.lower()


def _format_seconds_readable(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    try:
        total = int(seconds)
    except Exception:
        return str(seconds)

    if total <= 0:
        return "0 seconds"

    units = [
        ("year", 365 * 24 * 3600),
        ("month", 30 * 24 * 3600),
        ("day", 24 * 3600),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]

    parts = []
    remaining = total
    for name, unit_seconds in units:
        qty, remaining = divmod(remaining, unit_seconds)
        if qty:
            parts.append(f"{qty} {name}{'s' if qty != 1 else ''}")

    return ", ".join(parts)
