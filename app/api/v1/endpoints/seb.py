from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import Response, RedirectResponse, JSONResponse
from sqlmodel import Session, select
from app.api import deps
from app import models
from app.services.seb.seb_config import build_seb_config
from app.core import config as consts
from urllib.parse import urlparse

router = APIRouter()


# @router.get("/download/{session_id}")
@router.api_route("/download/{session_id}", methods=["GET", "HEAD"])
async def download_seb_config(
    session_id: str, session: Session = Depends(deps.get_session)
):
    interview_session = session.exec(
        select(models.InterviewSessions).where(
            models.InterviewSessions.interview_session_id == session_id
        )
    ).first()

    if not interview_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found."
        )

    interview_url = f"{consts.HOST}/welcome/{session_id}/"
    seb_bytes = build_seb_config(
        session_id, interview_url, interview_session.exam_exit_password
    )

    return Response(
        content=seb_bytes,
        media_type="application/seb",
        headers={
            "Content-Disposition": f"attachment; filename=interview_{session_id}.seb"
        },
    )


@router.get("/join/{session_id}")
async def join_interview_seb( 
    request: Request, session_id: str, session: Session = Depends(deps.get_session)
):

    domain = "http://172.16.1.101:51555"
    is_https = consts.PYTHON_BACKEND_URL.startswith("https")
    seb_proto = "sebs://" if is_https else "seb://"

    # seb_launch_url = f"sebs://2g7634mr-5002.inc1.devtunnels.ms/api/seb/download/{session_id}"
    seb_launch_url = f"{consts.HOST}/welcome/{session_id}/"
    # seb_launch_url = f"seb://2g7634mr-5002.inc1.devtunnels.ms/api/seb/download/{session_id}"
    # seb_launch_url = f"{seb_proto}{domain}/welcome/{session_id}"
    download_url = f"/api/seb/download/{session_id}"

    return JSONResponse(
        content={
            "success": True,
            "session_id": session_id,
            "seb_url": seb_launch_url,
            # "seb_url": f"seb://https://9snsrpwk-51555.inc1.devtunnels.ms/welcome/{session_id}/",
            # "download_url": download_url,
            "download_url": "https://safeexambrowser.org/download_en.html",
            # "join_url": f"https://5r4q0b3z-5002.inc1.devtunnels.ms/api/seb/join/{session_id}",
            # "interview_url": f"http://localhost:51555/welcome/{session_id}/",
            # "join_url": f"{consts.PYTHON_BACKEND_URL}/api/seb/join/{session_id}",
            # "interview_url": f"{consts.BASE_URL}/session/{session_id}/interview",
        }
    )


@router.get("/url/{session_id}")
async def get_seb_urls(session_id: str):
    domain = urlparse(consts.PYTHON_BACKEND_URL).netloc
    is_https = consts.PYTHON_BACKEND_URL.startswith("https")
    seb_proto = "sebs://" if is_https else "seb://"
    return {
        "seb_url": f"{seb_proto}{domain}/api/seb/download/{session_id}",
        # "join_url": f"{consts.PYTHON_BACKEND_URL}/api/seb/join/{session_id}",
        "join_url": f"https://2g7634mr-5002.inc1.devtunnels.ms/api/seb/join/{session_id}",
    }
