from sqlalchemy import update
from sqlmodel import select
from app import models
from app.services.minio_helper import delete_s3_object
import logging

logger = logging.getLogger(__name__)
def soft_delete_job_application(application_id: int, session):
    try:
        # --- Fetch Job Application ---
        job_app = session.exec(
            select(models.JobApplications).where(
                models.JobApplications.id == application_id,
                models.JobApplications.is_deleted == False
            )
        ).first()
        if not job_app:
            return False, "Job application not found"

        # --- Delete Resume from MinIO ---
        if job_app.resume:
            try:
                delete_s3_object(job_app.resume)
            except Exception as e:
                logger.error(f"MinIO delete failed: {e}")

        # --- Resume Tables ---
        session.exec(
            update(models.ResumeLogs)
            .where(models.ResumeLogs.application_id == application_id)
            .values(is_deleted=True)
        )

        session.exec(
            update(models.ResumeAttributes)
            .where(models.ResumeAttributes.application_id == application_id)
            .values(is_deleted=True)
        )

        session.exec(
            update(models.ResumeAnalysis)
            .where(models.ResumeAnalysis.application_id == application_id)
            .values(is_deleted=True)
        )

        # --- Interview Session ---
        session.exec(
            update(models.InterviewSessions)
            .where(models.InterviewSessions.application_id == application_id)
            .values(is_deleted=True)
        )

        # --- Interview Analysis ---
        interview_analysis = session.exec(
            select(models.InterviewAnalysis).where(
                models.InterviewAnalysis.application_id == application_id
            )
        ).first()

        if interview_analysis:
            session.exec(
                update(models.QNA_Analysis)
                .where(models.QNA_Analysis.interview_analysis_id == interview_analysis.id)
                .values(is_deleted=True)
            )

            session.exec(
                update(models.ProctoringLogs)
                .where(models.ProctoringLogs.interview_analysis_id == interview_analysis.id)
                .values(is_deleted=True)
            )

            session.exec(
                update(models.InterviewAnalysis)
                .where(models.InterviewAnalysis.id == interview_analysis.id)
                .values(is_deleted=True)
            )

        # --- Job Application ---
        session.exec(
            update(models.JobApplications)
            .where(models.JobApplications.id == application_id)
            .values(is_deleted=True)
        )

        return True, "Soft deleted successfully"

    except Exception as e:
        logger.error(f"Soft delete error: {e}")
        return False, str(e)
    

from sqlmodel import select
from app import models
from app.utils.delete_entries import soft_delete_job_application 
from app.services.minio_helper import delete_s3_object
from sqlalchemy import update
import logging
logger = logging.getLogger(__name__)

def delete_candidate_by_id(cid: int, session):
    try:
        # Candidate already employee?
        users_info = session.exec(
            select(models.User).where(models.User.candidate_id == cid)
        ).first()

        if users_info:
            return False, f"Candidate {cid} is already an employee, cannot delete"

        logger.info(f"No employee record found for candidate {cid}, proceeding")

        # Get candidate info
        candidate_info = session.exec(
            select(models.CandidateInfo).where(
                models.CandidateInfo.id == cid
            )
        ).first()

        if not candidate_info:
            return False, f"CandidateInfo {cid} not found"

        # Soft delete related job application
        application_id = candidate_info.application_id

        if application_id:
            job_app = session.exec(
                select(models.JobApplications).where(
                    models.JobApplications.id == application_id,
                    models.JobApplications.is_deleted == False
                )
            ).first()

            if job_app:
                success, message = soft_delete_job_application(job_app.id, session)

                if not success:
                    logger.error(
                        f"Failed to soft delete job application {job_app.id}: {message}"
                    )
                    return False, message

        # Soft delete Offer
        offers = session.exec(
            select(models.Offer).where(
                models.Offer.candidate_id == cid,
                models.Offer.is_deleted == False
            )
        ).all()

        for offer in offers:
            if offer.offer_letter_path:
                try:
                    delete_s3_object(offer.offer_letter_path)
                except Exception as e:
                    logger.error(f"Offer file delete failed: {e}")

            offer.is_deleted = True

        # Soft delete PreOnBoarding
        pre_onboarding = session.exec(
            select(models.PreOnBoarding).where(
                models.PreOnBoarding.candidate_id == cid,
                models.PreOnBoarding.is_deleted == False
            )
        ).all()

        for pre in pre_onboarding:
            pre.is_deleted = True

        # Soft delete BGV
        bgvs = session.exec(
            select(models.BGV).where(
                models.BGV.candidate_id == cid,
                models.BGV.is_deleted == False
            )
        ).all()

        for bgv in bgvs:
            if bgv.report_url:
                try:
                    delete_s3_object(bgv.report_url)
                except Exception as e:
                    logger.error(f"BGV file delete failed: {e}")

            bgv.is_deleted = True

        # Soft delete CandidateInfo
        candidate_info.is_deleted = True

        session.add(candidate_info)

        for offer in offers:
            session.add(offer)

        for pre in pre_onboarding:
            session.add(pre)

        for bgv in bgvs:
            session.add(bgv)

        session.commit()

        logger.info(f"Candidate {cid} soft deleted successfully")
        return True, f"Candidate {cid} soft deleted successfully"

    except Exception as e:
        session.rollback()
        logger.error(f"Delete candidate error: {e}")
        return False, str(e)

def delete_employee_by_candidate_id(cid: int, session):
    try:
        # --- 1. Check Employee Assets ---
        employee_asset = session.exec(
            select(models.EmployeeAssetsInfo).where(
                models.EmployeeAssetsInfo.id == cid
            )
        ).first()

        if employee_asset:
            return (
                False,
                f"Employee assets already assigned for candidate {cid}, cannot delete"
            )

        logger.info(f"No employee assets found for candidate {cid}")

        # --- 3. Get CandidateInfo ---
        candidate_info = session.exec(
            select(models.CandidateInfo).where(
                models.CandidateInfo.id == cid,
                models.CandidateInfo.is_deleted == False
            )
        ).first()

        # --- 4. Soft delete Job Application ---
        if candidate_info and candidate_info.application_id:
            job_app = session.exec(
                select(models.JobApplications).where(
                    models.JobApplications.id == candidate_info.application_id,
                    models.JobApplications.is_deleted == False
                )
            ).first()

            if job_app:
                success, message = soft_delete_job_application(
                    job_app.id,
                    session
                )

                if not success:
                    return False, message

        # --- 5. Soft delete BGV ---
        bgvs = session.exec(
            select(models.BGV).where(
                models.BGV.candidate_id == cid,
                models.BGV.is_deleted == False
            )
        ).all()

        for bgv in bgvs:
            if bgv.report_url:
                try:
                    delete_s3_object(bgv.report_url)
                except Exception as e:
                    logger.error(f"Failed to delete BGV file: {e}")

            bgv.is_deleted = True
            session.add(bgv)

        # --- 6. Soft delete Offers ---
        offers = session.exec(
            select(models.Offer).where(
                models.Offer.candidate_id == cid,
                models.Offer.is_deleted == False
            )
        ).all()

        for offer in offers:
            if offer.offer_letter_path:
                try:
                    delete_s3_object(offer.offer_letter_path)
                except Exception as e:
                    logger.error(f"Failed to delete Offer file: {e}")

            offer.is_deleted = True
            session.add(offer)

        # --- 7. Soft delete PreOnBoarding ---
        pre_records = session.exec(
            select(models.PreOnBoarding).where(
                models.PreOnBoarding.candidate_id == cid,
                models.PreOnBoarding.is_deleted == False
            )
        ).all()

        for pre in pre_records:
            pre.is_deleted = True
            session.add(pre)

        # --- 8. Soft delete CandidateInfo ---
        if candidate_info:
            candidate_info.is_deleted = True
            session.add(candidate_info)

        # --- 9. Soft delete users_info ---
        employee = session.exec(
            select(models.User).where(
        models.User.candidate_id == cid,
        models.User.is_deleted == False
            )
        ).first()
        if employee:
            employee.is_deleted = True
            session.add(employee)
            logger.info(f"users_info soft deleted for candidate {cid}")
        else:
            logger.warning(f"No users_info record found for candidate {cid}")

        session.commit()

        logger.info(f"Employee deleted successfully for candidate {cid}")
        return True, f"Employee deleted successfully for candidate {cid}"

    except Exception as e:
        session.rollback()
        logger.error(f"Employee delete error: {e}")
        return False, str(e)