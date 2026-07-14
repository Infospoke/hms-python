import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.resume_parser.s3_resume_parser import S3ResumeParser
from app.services.resume_parser.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)

router = APIRouter()

_resume_parser = S3ResumeParser()


def _score_one_resume(
    filename: str, file_bytes: bytes, job_description: str
) -> Dict[str, Any]:
    extension = Path(filename or "").suffix.lower()
    if extension not in _resume_parser.supported_formats:
        return {
            "success": False,
            "filename": filename,
            "error": (
                f"Unsupported file format '{extension}'. "
                f"Supported formats: {_resume_parser.supported_formats}"
            ),
            "final_score": 0,
            "recommendation": "REJECT",
        }
    if not file_bytes:
        return {
            "success": False,
            "filename": filename,
            "error": "Uploaded resume file is empty",
            "final_score": 0,
            "recommendation": "REJECT",
        }
    try:
        raw_text = _resume_parser._extract_text(BytesIO(file_bytes), extension)
        structured_text = _resume_parser._clean_text_preserve_layout(raw_text)
        metadata = _resume_parser._extract_metadata(structured_text)
        metadata["insufficient_text"] = metadata.get("word_count", 0) < 20
        metadata["file_size"] = round(len(file_bytes) / (1024 * 1024), 4)
        metadata["file_name"] = filename

        resume_data = {
            "success": True,
            "filename": filename,
            "text": structured_text,
            "metadata": metadata,
            "file_size": metadata["file_size"],
            "file_type": extension,
        }
        return ScoringEngine().score_resume(resume_data, job_description)
    except Exception as e:
        logger.error(f"Error analyzing {filename}: {str(e)}")
        return {
            "success": False,
            "filename": filename,
            "error": str(e),
            "final_score": 0,
            "recommendation": "REJECT",
        }


@router.post("/analyze")
async def test_analyze_resume(
    job_description: str = Form(...),
    resume: UploadFile = File(...),
):
    """
    Standalone resume analysis endpoint for testing/debugging.

    Takes a job description and a single resume file directly as input, runs
    them through the same parsing + scoring pipeline used in production
    (S3ResumeParser text extraction + ScoringEngine.score_resume with the
    configured LLM prompts), and returns the raw scoring result. No database
    reads or writes happen anywhere in this flow.
    """
    if not job_description or not job_description.strip():
        raise HTTPException(status_code=400, detail="job_description cannot be empty")

    file_bytes = await resume.read()
    return _score_one_resume(resume.filename, file_bytes, job_description)


@router.post("/analyze/bulk")
async def test_analyze_resumes_bulk(
    job_description: str = Form(...),
    resumes: List[UploadFile] = File(...),
):
    """
    Bulk version: scores multiple resumes against the same job description
    and returns a ranked report (highest final_score first) with summary
    stats, reusing the exact same parsing + scoring pipeline as the single
    endpoint above. No database reads or writes.
    """
    if not job_description or not job_description.strip():
        raise HTTPException(status_code=400, detail="job_description cannot be empty")
    if not resumes:
        raise HTTPException(status_code=400, detail="At least one resume file is required")

    try:
        file_payloads = [(f.filename, await f.read()) for f in resumes]

        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(len(file_payloads), 8)) as executor:
            futures = [
                executor.submit(_score_one_resume, filename, content, job_description)
                for filename, content in file_payloads
            ]
            for future in futures:
                results.append(future.result())

        results.sort(key=lambda r: r.get("final_score", 0) or 0, reverse=True)
        for idx, r in enumerate(results, start=1):
            r["rank"] = idx

        successful = [r for r in results if r.get("success")]
        recommendations = {"HIRE": 0, "CONSIDER": 0, "REJECT": 0}
        for r in results:
            rec = r.get("recommendation", "REJECT")
            recommendations[rec] = recommendations.get(rec, 0) + 1
        average_score = (
            round(sum(r.get("final_score", 0) for r in successful) / len(successful), 2)
            if successful
            else 0
        )

        return {
            "job_description": job_description,
            "total_resumes": len(results),
            "successful": len(successful),
            "failed": len(results) - len(successful),
            "average_score": average_score,
            "recommendations": recommendations,
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk test resume analysis: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
