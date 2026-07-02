"""SQLAlchemy ORM models for the AI Job Copilot database."""

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

from src.core.config import get_settings

settings = get_settings()
Base = declarative_base()


# ─── Enums ───────────────────────────────────────────────────────────────────


class SkillCategory(str, enum.Enum):
    TECHNICAL = "technical"
    FUNCTIONAL = "functional"
    BEHAVIORAL = "behavioral"
    CORE = "core"
    SUPPORTING = "supporting"


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ─── Models ──────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_id = Column(String(255), unique=True, nullable=False)  # Clerk's user ID (user_xxx)
    email = Column(String(255), unique=True, nullable=True)
    full_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    analyses = relationship("ATSAnalysis", back_populates="user", cascade="all, delete-orphan")
    skill_progress = relationship("SkillProgress", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_clerk_id", "clerk_id"),
    )


class Resume(Base):
    __tablename__ = "resumes"

    resume_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    parsed_text = Column(Text, nullable=True)
    parsed_sections = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    upload_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="resumes")
    analyses = relationship("ATSAnalysis", back_populates="resume", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="resume", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_resumes_user_id", "user_id"),
        Index("idx_resumes_upload_ts", "upload_timestamp"),
    )


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    jd_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    processed_text = Column(Text, nullable=True)
    parsed_requirements = Column(JSON, nullable=True)
    upload_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    analyses = relationship("ATSAnalysis", back_populates="job_description", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="job_description", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_jd_upload_ts", "upload_timestamp"),
        Index("idx_jd_user_id", "user_id"),
    )


class Skill(Base):
    __tablename__ = "skills"

    skill_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_name = Column(String(255), nullable=False, unique=True)
    skill_name_normalized = Column(String(255), nullable=False)
    skill_category = Column(SQLEnum(SkillCategory), nullable=False, default=SkillCategory.TECHNICAL)
    description = Column(Text, nullable=True)
    synonyms = Column(JSON, nullable=True)  # List of alternative names
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    analysis_skills = relationship("AnalysisSkill", back_populates="skill")

    __table_args__ = (
        Index("idx_skills_name", "skill_name"),
        Index("idx_skills_category", "skill_category"),
        Index("idx_skills_normalized", "skill_name_normalized"),
    )


class ATSAnalysis(Base):
    __tablename__ = "ats_analyses"

    analysis_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.resume_id", ondelete="CASCADE"), nullable=False)
    jd_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.jd_id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(SQLEnum(AnalysisStatus), nullable=False, default=AnalysisStatus.PENDING)
    overall_score = Column(Float, nullable=True)
    keyword_score = Column(Float, nullable=True)
    semantic_score = Column(Float, nullable=True)
    category_scores = Column(JSON, nullable=True)
    matched_skills = Column(JSON, nullable=True)
    missing_skills = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)
    evidence = Column(JSON, nullable=True)
    explainability_report = Column(JSON, nullable=True)
    optimized_bullets = Column(JSON, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="analyses")
    resume = relationship("Resume", back_populates="analyses")
    job_description = relationship("JobDescription", back_populates="analyses")
    skills = relationship("AnalysisSkill", back_populates="analysis", cascade="all, delete-orphan")
    quiz_results = relationship("QuizResult", back_populates="analysis", cascade="all, delete-orphan")
    feedback = relationship("AnalysisFeedback", back_populates="analysis", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_analysis_user_id", "user_id"),
        Index("idx_analysis_resume", "resume_id"),
        Index("idx_analysis_jd", "jd_id"),
        Index("idx_analysis_status", "status"),
        Index("idx_analysis_created", "created_at"),
    )


class AnalysisSkill(Base):
    """Junction table linking analyses to skills with match metadata."""

    __tablename__ = "analysis_skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ats_analyses.analysis_id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id = Column(UUID(as_uuid=True), ForeignKey("skills.skill_id", ondelete="CASCADE"), nullable=False)
    source = Column(String(50), nullable=False)  # 'resume' or 'job_description'
    confidence = Column(Float, nullable=False, default=0.0)
    matched = Column(String(20), nullable=True)  # 'exact', 'semantic', 'missing'
    evidence_text = Column(Text, nullable=True)

    # Relationships
    analysis = relationship("ATSAnalysis", back_populates="skills")
    skill = relationship("Skill", back_populates="analysis_skills")

    __table_args__ = (
        Index("idx_analysis_skills_analysis", "analysis_id"),
        Index("idx_analysis_skills_skill", "skill_id"),
    )


class DocumentChunk(Base):
    """Stores chunked text with vector embeddings for RAG."""

    __tablename__ = "document_chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.resume_id", ondelete="CASCADE"), nullable=True)
    jd_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.jd_id", ondelete="CASCADE"),
        nullable=True,
    )
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    section_type = Column(String(100), nullable=True)  # e.g., 'experience', 'skills', 'requirements'
    embedding = Column(Vector(settings.OPENAI_EMBEDDING_DIMENSIONS), nullable=True)
    chunk_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    resume = relationship("Resume", back_populates="chunks")
    job_description = relationship("JobDescription", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_resume", "resume_id"),
        Index("idx_chunks_jd", "jd_id"),
        Index("idx_chunks_section", "section_type"),
    )


class QuizResult(Base):
    __tablename__ = "quiz_results"

    quiz_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    analysis_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ats_analyses.analysis_id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_tested = Column(String(255), nullable=False)
    difficulty = Column(String(20), nullable=False, default="easy")  # easy, medium, hard
    questions = Column(JSON, nullable=False)
    answers = Column(JSON, nullable=True)
    score = Column(Float, nullable=True)
    passed = Column(String(10), nullable=True)  # 'pass', 'fail', 'partial'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    analysis = relationship("ATSAnalysis", back_populates="quiz_results")

    __table_args__ = (
        Index("idx_quiz_analysis", "analysis_id"),
        Index("idx_quiz_user_id", "user_id"),
        Index("idx_quiz_skill", "skill_tested"),
    )


class SkillProgress(Base):
    """Tracks a user's quiz progression per skill across all analyses."""

    __tablename__ = "skill_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    skill_name = Column(String(255), nullable=False)
    # True when the skill was later found present in a newer resume (no longer a gap)
    is_resolved = Column(Boolean, nullable=False, default=False)
    # highest difficulty passed: none, easy, medium, hard
    highest_level_passed = Column(String(20), nullable=False, default="none")
    # ready_to_apply = passed hard level → can add to resume via project
    ready_to_apply = Column(String(5), nullable=False, default="false")
    easy_passed_at = Column(DateTime, nullable=True)
    medium_passed_at = Column(DateTime, nullable=True)
    hard_passed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="skill_progress")

    __table_args__ = (
        Index("idx_skill_progress_user", "user_id"),
        Index("idx_skill_progress_skill", "skill_name"),
        # One row per user per skill
        Index("idx_skill_progress_user_skill", "user_id", "skill_name", unique=True),
    )


class AnalysisFeedback(Base):
    """Stores recruiter/user feedback for the feedback loop."""

    __tablename__ = "analysis_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ats_analyses.analysis_id", ondelete="CASCADE"),
        nullable=False,
    )
    feedback_type = Column(String(50), nullable=False)  # 'score_adjustment', 'weight_change', 'general'
    original_score = Column(Float, nullable=True)
    revised_score = Column(Float, nullable=True)
    weight_adjustments = Column(JSON, nullable=True)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    analysis = relationship("ATSAnalysis", back_populates="feedback")

    __table_args__ = (Index("idx_feedback_analysis", "analysis_id"),)


class CacheEntry(Base):
    """Tracks caching metrics."""

    __tablename__ = "cache_entries"

    cache_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cache_key = Column(String(512), unique=True, nullable=False)
    cache_type = Column(String(50), nullable=False)  # 'jd_parse', 'resume_parse', 'embedding', 'analysis'
    hit_count = Column(Integer, default=0, nullable=False)
    miss_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_accessed = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_cache_key", "cache_key"),
        Index("idx_cache_type", "cache_type"),
    )


class UserFeedback(Base):
    """General user feedback and suggestions about the product."""

    __tablename__ = "user_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)
    category = Column(String(50), nullable=False, default="general")  # bug, suggestion, general
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_user_feedback_user", "user_id"),
        Index("idx_user_feedback_created", "created_at"),
    )
