import logging
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.exc import OperationalError, DatabaseError
from sqlalchemy import text
from app.core.exceptions import DatabaseConnectionException, DatabaseException
from app.core import config as consts

# --- DATABASE ENGINE ---
logger = logging.getLogger(__name__)
DATABASE_URL = consts.DATABASE_URL
connect_args = {}
if DATABASE_URL and isinstance(DATABASE_URL, str) and "sqlite" in DATABASE_URL:
    connect_args["check_same_thread"] = False
try:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        connect_args=connect_args,
        pool_size=50,
        max_overflow=20,
        pool_pre_ping=True,
    )
    logger.debug(f"Database engine created successfully")
except Exception as e:
    logger.error(f"Failed to create database engine: {str(e)}")
    raise DatabaseConnectionException(consts.DB_INIT_FAILED(e))


# --- DATABASE INITIALIZATION ---


def create_db_and_tables():
    try:
        with engine.begin() as conn:
            SQLModel.metadata.create_all(conn)
            conn.execute(text("COMMIT"))
        logger.debug("Database tables created/verified successfully")
    except OperationalError as e:
        logger.error(f"Database operation error during table creation: {str(e)}")
        raise DatabaseConnectionException(consts.DB_CREATE_TABLE_FAILED(e))
    except DatabaseError as e:
        logger.error(f"Database error during table creation: {str(e)}")
        raise DatabaseException(consts.DB_INIT_ERROR(e))
    except Exception as e:
        logger.error(f"Unexpected error during table creation: {str(e)}")
        raise DatabaseException(consts.DB_CREATE_TABLE_FAILED(e))


# --- DATABASE SESSION MANAGEMENT ---


def get_session():
    session = None
    try:
        session = Session(engine)
        yield session
    except OperationalError as e:
        logger.error(f"Database operation error: {str(e)}")
        if session:
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {str(rollback_error)}")
        raise
    except DatabaseError as e:
        logger.error(f"Database error: {str(e)}")
        if session:
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {str(rollback_error)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database session: {str(e)}")
        if session:
            try:
                session.rollback()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {str(rollback_error)}")
        raise
    finally:
        if session:
            try:
                session.close()
            except Exception as e:
                logger.error(f"Error closing database session: {str(e)}")
