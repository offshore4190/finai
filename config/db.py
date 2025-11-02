"""
Database connection and session management.
"""
from contextlib import contextmanager
from typing import Generator

import structlog
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from config.settings import settings

logger = structlog.get_logger()

# SQLAlchemy base for models
Base = declarative_base()

# Create engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Set connection parameters on new connections."""
    # This is mainly for PostgreSQL-specific settings if needed
    pass


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Usage:
        with get_db_session() as session:
            session.query(...)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("database_session_error", error=str(e))
        raise
    finally:
        session.close()


def init_db():
    """
    Initialize database by creating all tables.
    For production, use migrations instead.
    """
    logger.info("initializing_database")
    Base.metadata.create_all(bind=engine)
    logger.info("database_initialized")


def execute_schema_file(schema_path: str):
    """
    Execute SQL schema file directly.
    
    Args:
        schema_path: Path to SQL file
    """
    logger.info("executing_schema_file", path=schema_path)
    
    with open(schema_path, 'r') as f:
        sql = f.read()
    
    with engine.begin() as conn:
        # Split by semicolon and execute each statement
        for statement in sql.split(';'):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    
    logger.info("schema_file_executed", path=schema_path)
