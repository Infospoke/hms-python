import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
from fastapi import FastAPI
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.responses import Response as StarletteResponse
from sqlalchemy.exc import (
    IntegrityError,
    SQLAlchemyError,
    OperationalError,
    DatabaseError,
)
import logging
from app.core import config as consts
from app.api.v1.api import api_router
from app.db.session import create_db_and_tables
from app.core.exceptions import (
    DatabaseConnectionException,
    DatabaseQueryException,
    DatabaseIntegrityException,
    ResourceNotFoundException,
    DuplicateResourceException,
    ValidationException,
    FileOperationException,
    HTTPClientException,
    DatabaseException,
)
import os
import threading

if os.path.exists("logging.conf"):
    logging.config.fileConfig("logging.conf", disable_existing_loggers=False)

# --- APP INITIALIZATION ---
logger = logging.getLogger(__name__)
app = FastAPI(title=consts.PROJECT_NAME, openapi_url=f"/api/v1/openapi.json")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # allowed origins
    allow_credentials=True,
    allow_methods=["*"],          # GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],          # all headers
)




@app.middleware("http")
async def config_refresh_middleware(request: Request, call_next):
    consts.refresh_configs_if_needed()
    response = await call_next(request)
    return response


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(
        f"{request.method} {request.url.path} "
        f"origin={request.headers.get('origin', '-')} "
        f"status={response.status_code} {duration}ms"
    )
    return response


app.include_router(api_router, prefix="/api")


# --- STARTUP LOGIC ---
@app.on_event("startup")
def on_startup():
    try:
        create_db_and_tables()
        logger.debug("Database initialization successful")

        consts._load_interview_configs()
        logger.debug(f"Interview configs loaded successfully.")

        if consts.MAX_QUESTION_TIME is None:
            logger.warning(
                "MAX_QUESTION_TIME not found in interview_configurations table - "
                "consts.MAX_QUESTION_TIME will be None until a refresh is triggered."
            )

        if consts.IMAGE_PROCTORING_TIME_WINDOW is None:
            logger.warning(
                "IMAGE_PROCTORING_TIME_WINDOW not found in interview_configurations table - "
                "consts.IMAGE_PROCTORING_TIME_WINDOW will be None until a refresh is triggered."
            )

        logger.debug(
            "analyze_image_worker setup skipped in FastAPI. Use run_workers.py to start."
        )

        logger.debug(
            "AnalysisWorker setup skipped in FastAPI. Use run_workers.py to start."
        )
    except DatabaseException as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during startup: {str(e)}")
        raise


@app.on_event("shutdown")
def on_shutdown():
    logger.info("FastAPI shutdown event triggered. Cleaning up connections...")
    try:
        from app.services import kafka_helper

        kafka_helper.close_kafka_producer()
    except Exception as e:
        logger.error(f"Error during shutdown cleanup: {e}")


# --- EXCEPTION HANDLERS ---


@app.exception_handler(DatabaseConnectionException)
async def database_connection_exception_handler(request, exc):
    logger.error(f"Database connection error: {exc.message}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database connection failed. Please try again later."},
    )


@app.exception_handler(DatabaseQueryException)
async def database_query_exception_handler(request, exc):
    logger.error(f"Database query error ({exc.query_type}): {exc.message}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database operation failed. Please try again."},
    )


@app.exception_handler(DatabaseIntegrityException)
async def database_integrity_exception_handler(request, exc):
    logger.error(f"Database integrity error: {exc.message}")
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.exception_handler(ResourceNotFoundException)
async def resource_not_found_handler(request, exc):
    logger.warning(f"Resource not found: {exc.message}")
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(DuplicateResourceException)
async def duplicate_resource_handler(request, exc):
    logger.warning(f"Duplicate resource: {exc.message}")
    return JSONResponse(status_code=409, content={"detail": exc.message})


@app.exception_handler(ValidationException)
async def validation_exception_handler(request, exc):
    logger.warning(f"Validation error: {exc.message}")
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.exception_handler(FileOperationException)
async def file_operation_exception_handler(request, exc):
    logger.error(f"File operation error: {exc.message}")
    return JSONResponse(
        status_code=500, content={"detail": "File operation failed. Please try again."}
    )


@app.exception_handler(HTTPClientException)
async def http_client_exception_handler(request, exc):
    logger.error(f"HTTP client error: {exc.message}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(OperationalError)
async def operational_error_handler(request, exc):
    logger.error(f"Database operational error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database operation failed. Please try again later."},
    )


@app.exception_handler(DatabaseError)
async def database_error_handler(request, exc):
    logger.error(f"Database error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database error occurred. Please try again later."},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request, exc):
    logger.error(f"Database integrity constraint violation: {str(exc)}")
    return JSONResponse(
        status_code=400, content={"detail": "Invalid data: constraint violation"}
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request, exc):
    logger.error(f"SQLAlchemy error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Database error occurred. Please try again later."},
    )
