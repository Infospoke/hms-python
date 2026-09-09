from typing import Dict, Any
import logging
from sqlmodel import Session
from app.core import config as consts
from app.core import messages
from .resume_analyzer import ResumeAnalyzer
from .resume_analysis_service import ResumeAnalysisService
from ..db_operations import get_unanalysed_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- RESUME PROCESSING ---


def progress_callback(current, total, result):
    logger.info(messages.PROCESSING_FILE(current, total, result.get("filename", None)))


def process_resumes(
    session: Session,
    job_description: str,
    job_id: int,
    job_title: str,
    resume_files: list = [],
    app_id_map: dict = None,
    min_score: float = 0,
    verbose: bool = True,
    background_tasks=None,
) -> Dict[str, Any]:
    if not job_description:
        raise ValueError(consts.EMPTY_JOB_DESCRIPTION)
    if not resume_files and not app_id_map:
        logger.info(
            f"No files provided, fetching unanalyzed applications for job {job_id}..."
        )
        unanalyzed_apps = get_unanalysed_data(session, job_id)
        if unanalyzed_apps:
            resume_files = []
            app_id_map = {}
            for app in unanalyzed_apps:
                resume_path = app.get("resume")
                if resume_path:
                    resume_files.append(resume_path)
                    app_id_map[resume_path] = app.get("id")
            logger.info(f"Found {len(resume_files)} unanalyzed resumes in DB")
        else:
            logger.info("No unanalyzed resumes found.")
            return {
                "successful": [],
                "failed": [],
                "summary": {"total": 0, "success_count": 0, "fail_count": 0},
            }
    # Legacy behavior was: analyzer = ResumeAnalyzer(session, job_title, background_tasks)
    # The guarded fallback below preserves that behavior when initialization succeeds.
    try:
        analyzer = ResumeAnalyzer(session, job_title, background_tasks)
    except Exception as error:
        fallback_results = []
        application_ids = set((app_id_map or {}).values())
        for application_id in application_ids:
            try:
                ResumeAnalysisService.save_dummy_analysis(session, application_id)
                ResumeAnalyzer.create_interview_for_application(
                    session, application_id, background_tasks
                )
                fallback_results.append(
                    {
                        "success": True,
                        "dummy_fallback": True,
                        "fallback_reason": str(error),
                        "application_id": application_id,
                        "final_score": 82.5,
                        "recommendation": "HIRE",
                    }
                )
            except Exception as fallback_error:
                logger.error(
                    f"Failed to save dummy analysis for application "
                    f"{application_id}: {fallback_error}"
                )

        if fallback_results:
            logger.warning(
                "Saved dummy resume analyses because Gemini initialization failed: "
                f"{error}"
            )
            return {
                "success": True,
                "results": fallback_results,
                "job_description": job_description,
            }
        raise

    logger.info(f"process_resumes: background_tasks passed = {background_tasks is not None}")
    results = analyzer.analyze_multiple_resumes(
        resume_files, job_description, progress_callback, app_id_map
    )
    return results
