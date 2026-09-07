import logging
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.exc import OperationalError, DatabaseError
from sqlalchemy import text
from app.core.exceptions import DatabaseConnectionException, DatabaseException, ATSException
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


def _auto_migrate_schema(conn):
    """
    Inspects existing database tables and automatically:
    1. Adds missing columns with defaults.
    2. Alters column types / nullability if modified in SQLModel models.
    3. Adds missing unique constraints.
    4. Adds missing foreign key relationships.
    """
    from sqlalchemy import inspect
    import app.models  # Ensures all SQLModel models are registered

    try:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        for table_name, table in SQLModel.metadata.tables.items():
            if table_name not in existing_tables:
                continue

            # 1. Fetch existing column metadata
            db_columns_info = {col["name"]: col for col in inspector.get_columns(table_name)}
            existing_column_names = set(db_columns_info.keys())

            # 2. Fetch existing foreign keys
            try:
                existing_fks = inspector.get_foreign_keys(table_name)
                existing_fk_cols = {
                    fk.get("constrained_columns", [None])[0]: (
                        fk.get("referred_table"),
                        fk.get("referred_columns", [None])[0],
                    )
                    for fk in existing_fks
                    if fk.get("constrained_columns")
                }
            except Exception:
                existing_fk_cols = {}

            # 3. Fetch existing unique constraints
            try:
                existing_uniques = {
                    uq.get("column_names", [None])[0]
                    for uq in inspector.get_unique_constraints(table_name)
                    if uq.get("column_names") and len(uq["column_names"]) == 1
                }
            except Exception:
                existing_uniques = set()

            for column in table.columns:
                col_type = column.type.compile(conn.dialect)

                # --- A. ADD MISSING COLUMNS ---
                if column.name not in existing_column_names:
                    try:
                        default_clause = ""
                        if column.server_default is not None:
                            default_clause = f"DEFAULT {column.server_default.arg}"
                        elif column.default is not None and getattr(column.default, "arg", None) is not None:
                            val = column.default.arg
                            if isinstance(val, str):
                                default_clause = f"DEFAULT '{val}'"
                            elif isinstance(val, bool):
                                default_clause = f"DEFAULT {'TRUE' if val else 'FALSE'}"
                            elif isinstance(val, (int, float)):
                                default_clause = f"DEFAULT {val}"

                        sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column.name}" {col_type} {default_clause};'
                        logger.info(f"Auto-migrating missing column: {table_name}.{column.name} ({col_type})")
                        conn.execute(text(sql))
                    except Exception as col_err:
                        logger.warning(f"Could not auto-add column {table_name}.{column.name}: {col_err}")

                # --- B. ALTER COLUMN TYPE IF CHANGED ---
                else:
                    db_col = db_columns_info.get(column.name, {})
                    db_type_str = str(db_col.get("type", "")).upper()
                    model_type_str = str(column.type).upper()

                    # Check if type significantly differs (e.g. length increase, text vs varchar)
                    if db_type_str and model_type_str and db_type_str != model_type_str:
                        try:
                            alter_type_sql = f'ALTER TABLE "{table_name}" ALTER COLUMN "{column.name}" TYPE {col_type} USING "{column.name}"::{col_type};'
                            conn.execute(text(alter_type_sql))
                            logger.info(f"Auto-migrated column type: {table_name}.{column.name} to {col_type}")
                        except Exception as alter_err:
                            logger.debug(f"Could not alter column type {table_name}.{column.name}: {alter_err}")

                # --- C. ADD MISSING UNIQUE CONSTRAINTS ---
                if column.unique and column.name not in existing_uniques:
                    constraint_name = f"uq_{table_name}_{column.name}"
                    sql = f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" UNIQUE ("{column.name}");'
                    try:
                        conn.execute(text(sql))
                        logger.info(f"Auto-migrated unique constraint: {table_name}.{column.name}")
                        existing_uniques.add(column.name)
                    except Exception as uq_err:
                        logger.debug(f"Could not add unique constraint {constraint_name}: {uq_err}")

                # --- D. ADD MISSING FOREIGN KEYS ---
                for fk in column.foreign_keys:
                    target_table = fk.column.table.name
                    target_col = fk.column.name
                    if target_table in existing_tables:
                        if column.name not in existing_fk_cols:
                            fk_name = f"fk_{table_name}_{column.name}_{target_table}"
                            sql = f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{fk_name}" FOREIGN KEY ("{column.name}") REFERENCES "{target_table}" ("{target_col}");'
                            try:
                                conn.execute(text(sql))
                                logger.info(f"Auto-migrated foreign key: {table_name}.{column.name} -> {target_table}.{target_col}")
                                existing_fk_cols[column.name] = (target_table, target_col)
                            except Exception as fk_err:
                                logger.debug(f"Could not add foreign key {fk_name}: {fk_err}")

    except Exception as e:
        logger.warning(f"Error during auto-migration of database schema: {str(e)}")


def create_db_and_tables():
    try:
        with engine.begin() as conn:
            # 1. Creates any new tables that do not exist yet
            SQLModel.metadata.create_all(conn)

            # 2. Automatically syncs columns, types, constraints, and foreign keys
            _auto_migrate_schema(conn)

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
        exc_type_name = type(e).__name__
        is_expected_error = (
            exc_type_name in ("HTTPException", "RequestValidationError", "ValidationError")
            or isinstance(e, ATSException)
        )
        if not is_expected_error:
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
