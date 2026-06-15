import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.core import config as consts
from app import models
from app.services import db_operations
from sqlmodel import Session, select
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html", "xml"])
)


def get_mail_config():
    """
    Returns the FastMail connection configuration, ensuring latest settings
    from the database are applied.
    """
    consts.refresh_configs_if_needed()
    return ConnectionConfig(
        MAIL_USERNAME=consts.MAIL_USERNAME or "",
        MAIL_PASSWORD=consts.MAIL_PASSWORD or "",
        MAIL_FROM=consts.MAIL_FROM or "",
        MAIL_PORT=consts.MAIL_PORT or 587,
        MAIL_SERVER=consts.MAIL_SERVER or "",
        MAIL_STARTTLS=consts.MAIL_STARTTLS if consts.MAIL_STARTTLS is not None else True,
        MAIL_SSL_TLS=consts.MAIL_SSL_TLS if consts.MAIL_SSL_TLS is not None else False,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )


async def send_email(
    subject: str, template_name: str, context: dict, recipients: list[str], attachments: list = []
):
    try:
        template = env.get_template(template_name)
        html_content = template.render(context)

        message = MessageSchema(
            subject=subject,
            recipients=recipients,
            body=html_content,
            subtype="html",
            attachments=attachments
        )

        fm = FastMail(get_mail_config())
        await fm.send_message(message)
        logger.info(f"Email sent: {template_name}")
        return True
    except Exception as err:
        logger.error(f"Error sending email: {err}")
        return False


def get_candidate_details(application_id: int, db_session: Session):
    job_application = db_session.exec(
        select(models.JobApplications).where(
            models.JobApplications.id == application_id
        )
    ).first()
    job_details = db_session.exec(
        select(models.JobDetails).where(
            models.JobDetails.job_id == job_application.job_id
        )
    ).first()
    job_title = db_operations.get_job_title(db_session, job_details.job_id)
    candidate_name = f"{job_application.first_name} {job_application.last_name}"
    candidate_email = job_application.email
    return job_title, candidate_name, candidate_email


from sqlmodel import select


def get_cutoff_score(db_session: Session) -> int:
    config = db_session.exec(
        select(models.InterviewConfiguration).where(
            models.InterviewConfiguration.configuration_name == "INTERVIEW_CUTOFF_SCORE"
        )
    ).first()

    return int(config.configuration_value) if config else 50
