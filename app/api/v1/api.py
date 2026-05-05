from fastapi import APIRouter
from app.api.v1.endpoints import resume, interview, admin, seb, report

api_router = APIRouter()
api_router.include_router(resume.router, prefix="/resume", tags=["resume"])
api_router.include_router(interview.router, prefix="/interview", tags=["interview"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(seb.router, prefix="/seb", tags=["seb"])
api_router.include_router(report.router, prefix="/report", tags=["report"])
