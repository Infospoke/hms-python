from sqlmodel import Session, select
import logging
from app import models
from app.db.session import engine
from app.core import config as consts
from .processor import process_resumes
import os
from typing import List
from collections import defaultdict

# logging.basicConfig(
#     level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# )
logger = logging.getLogger(__name__)


# --- BATCH ANALYZER ---


class BatchAnalyzer:

    def __init__(self, background_tasks=None):
        self.engine = engine
        self.background_tasks = background_tasks
        logger.info(f"BatchAnalyzer initialized with background_tasks: {background_tasks is not None}")

    def _construct_job_description_for_llm(
        self,
        job_title,
        job_info,
        job_description,
        job_requirements,
        qualification,
        skills,
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

    def analyze_job_applications(self, job_ids: List[int]):
        with Session(self.engine) as session:
            failed_analysis_count = 0
            analysis = defaultdict(list)
            for job_id in job_ids:
                job_details = session.exec(
                    select(models.JobDetails).where(models.JobDetails.job_id == job_id)
                ).first()
                if not job_details:
                    logger.error(f"Job with ID {job_id} not found.")
                    return

                job = session.exec(
                    select(models.Jobs).where(models.Jobs.job_id == job_details.job_id)
                ).first()

                job_description_for_llm = self._construct_job_description_for_llm(
                    job.job_title,
                    job.job_info,
                    job_details.job_description,
                    job_details.job_requirements,
                    job_details.qualification,
                    job_details.skills,
                )
                logger.info(
                    f"Analyzing applications for job: {job.job_title} (ID: {job_id})"
                )
                result = process_resumes(
                    session=session,
                    job_description=job_description_for_llm,
                    job_id=job_details.job_id,
                    job_title=job.job_title,
                    resume_files=[],
                    app_id_map=None,
                    verbose=True,
                    background_tasks=self.background_tasks,
                )
                if not result.get("success", True):
                    analysis["unable_to_analyze_job_id"].append(job_id)
                    failed_analysis_count += 1
                analysis["results"].append(result)
                logger.info(f"Batch analysis completed for Job {job_id}")
            analysis["success"] = not failed_analysis_count == len(job_ids)
            return analysis

    def analyze_all_jobs(self):
        with Session(self.engine) as session:
            jobs = session.exec(select(models.JobDetails)).all()
            for job in jobs:
                self.analyze_job_applications([job.job_id])

    def analyze_job_applications_batch(self, resume_batch, batch_id):
        with Session(self.engine) as session:
            statement = select(models.JobApplications).where(
                models.JobApplications.id.in_(resume_batch)
            )
            applications = session.exec(statement).all()
            if not applications:
                return {
                    "message": consts.NO_JOB_APPLICATIONS_FOUND,
                    "batch_id": batch_id,
                    "results": [],
                    "success": False,
                }
            apps_by_job = {}
            for app in applications:
                if app.job_id not in apps_by_job:
                    apps_by_job[app.job_id] = []
                apps_by_job[app.job_id].append(app)
            all_results = []
            for job_id, apps in apps_by_job.items():
                job_details = session.exec(
                    select(models.JobDetails).where(models.JobDetails.job_id == job_id)
                ).first()
                if not job_details:
                    for app in apps:
                        all_results.append(
                            {
                                "success": False,
                                "error": consts.NO_JOB_DETAILS_FOUND_FOR_JOB_ID(job_id),
                                "application_id": app.id,
                            }
                        )
                    continue
                resume_files = []
                app_id_map = {}
                for app in apps:
                    if app.resume:
                        full_path = app.resume

                        resume_files.append(full_path)
                        app_id_map[full_path] = app.id
                    else:
                        all_results.append(
                            {
                                "success": False,
                                "error": consts.NO_RESUME_FILE_PATH_IN_APPLICATION,
                                "application_id": app.id,
                            }
                        )
                job = session.exec(
                    select(models.Jobs).where(models.Jobs.job_id == job_details.job_id)
                ).first()

                if resume_files:
                    job_description_for_llm = self._construct_job_description_for_llm(
                        job.job_title,
                        job.job_info,
                        job_details.job_description,
                        job_details.job_requirements,
                        job_details.qualification,
                        job_details.skills,
                    )
                    job_results = process_resumes(
                        session=session,
                        job_description=job_description_for_llm,
                        job_id=job.job_id,
                        job_title=job.job_title,
                        resume_files=resume_files,
                        app_id_map=app_id_map,
                        verbose=True,
                        background_tasks=self.background_tasks,
                    )
                    if "results" in job_results:
                        all_results.extend(job_results["results"])
            return {
                "message": consts.BATCH_RESUMES_ANALYZED,
                "batch_id": batch_id,
                "results": all_results,
                "success": True,
            }
