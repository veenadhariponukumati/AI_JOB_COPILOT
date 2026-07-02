"""Database initialization script.

Creates all tables and enables the pgvector extension.
Run this script to set up the database schema.
"""

from sqlalchemy import text

from src.core.logger import get_logger
from src.database.models import Base
from src.database.session import engine

logger = get_logger(__name__)


def init_database():
    """Initialize the database with all tables and extensions."""
    try:
        # Enable extensions (pgvector may not be installed locally - non-fatal)
        with engine.connect() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                logger.info("pgvector extension enabled")
            except Exception as ext_err:
                logger.warning(f"pgvector not available (RAG embeddings disabled): {ext_err}")
                conn.rollback()
            try:
                conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
                conn.commit()
                logger.info("uuid-ossp extension enabled")
            except Exception as ext_err:
                logger.warning(f"uuid-ossp not available: {ext_err}")
                conn.rollback()

        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("All database tables created successfully.")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def drop_database():
    """Drop all tables (use with caution)."""
    Base.metadata.drop_all(bind=engine)
    logger.info("All database tables dropped.")


if __name__ == "__main__":
    init_database()
