"""Application configuration management."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "AI Job Copilot"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ATS_DEBUG_TRACE: bool = False

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_job_copilot"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536

    # RAG Configuration
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50
    TOP_K_RETRIEVAL: int = 5
    SIMILARITY_THRESHOLD: float = 0.7

    # Scoring Weights
    KEYWORD_WEIGHT: float = 0.4
    SEMANTIC_WEIGHT: float = 0.4
    CATEGORY_WEIGHT: float = 0.2

    # Clerk Auth
    CLERK_FRONTEND_API: str = ""  # e.g. "your-app.clerk.accounts.dev"
    CLERK_SECRET_KEY: str = ""  # sk_live_xxx or sk_test_xxx

    # Caching
    CACHE_TTL_SECONDS: int = 3600
    CACHE_MAX_SIZE: int = 1000

    # Skill Extraction
    SKILL_CONFIDENCE_THRESHOLD: float = 0.6
    MAX_SKILLS_PER_DOCUMENT: int = 50

    # Email (Resend) - used to notify the site owner of new feedback
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    FEEDBACK_NOTIFY_EMAIL: str = "veenadhariponukumati@gmail.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
