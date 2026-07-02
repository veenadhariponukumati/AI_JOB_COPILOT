"""API response schemas (Pydantic models)."""

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class BaseResponse(BaseModel):
    """Base response with status and message."""

    success: bool = True
    message: str = "OK"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ResumeUploadResponse(BaseResponse):
    """Response after resume upload."""

    resume_id: UUID
    parsed_sections: List[str] = []
    skill_count: int = 0
    char_count: int = 0


class JobDescriptionUploadResponse(BaseResponse):
    """Response after job description upload."""

    jd_id: UUID
    title: Optional[str] = None
    parsed_sections: List[str] = []
    requirement_count: int = 0


class SkillDetail(BaseModel):
    """Detail of a single skill match."""

    skill: str
    category: str = "unknown"
    match_type: Optional[str] = None
    matched_by: Optional[str] = None
    match_reason: Optional[str] = None
    missing_reason: Optional[str] = None
    confidence: Optional[float] = None
    evidence: Optional[str] = None
    evidence_from_resume: Optional[str] = None


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown."""

    overall_score: float
    keyword_score: float
    semantic_score: float
    category_scores: Dict[str, Any] = {}


class AnalysisResponse(BaseResponse):
    """Response for ATS analysis results."""

    analysis_id: UUID
    status: str
    score: Optional[ScoreBreakdown] = None
    matched_skills: List[SkillDetail] = []
    missing_skills: List[SkillDetail] = []
    recommendations: List[str] = []
    explainability: Optional[Dict] = None
    evidence: List[Dict] = []
    optimized_bullets: List[Dict] = []
    processing_time_ms: Optional[int] = None


class QuizQuestion(BaseModel):
    """A single quiz question."""

    question_id: int
    question: str
    options: List[str]
    difficulty: str = "medium"


class QuizStartResponse(BaseResponse):
    """Response when starting a quiz."""

    quiz_id: UUID
    skill: str
    questions: List[QuizQuestion]
    total_questions: int


class QuizResultResponse(BaseResponse):
    """Response after submitting quiz answers."""

    quiz_id: UUID
    score: float
    passed: str
    correct_answers: int
    total_questions: int
    details: List[Dict] = []


class HistoryItem(BaseModel):
    """A single analysis history entry."""

    analysis_id: UUID
    resume_filename: Optional[str] = None
    jd_title: Optional[str] = None
    overall_score: Optional[float] = None
    status: str
    created_at: datetime


class HistoryResponse(BaseResponse):
    """Response for analysis history."""

    total: int
    items: List[HistoryItem] = []


class CacheMetricsResponse(BaseResponse):
    """Response for cache metrics."""

    metrics: Dict[str, Any] = {}


class EvaluationReportResponse(BaseResponse):
    """Response for evaluation report."""

    report: Dict[str, Any] = {}


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[Dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
