"""API request schemas (Pydantic models)."""

from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ResumeUploadRequest(BaseModel):
    """Request schema for resume upload."""

    text: str = Field(..., min_length=50, description="Resume text content")
    filename: Optional[str] = Field(None, description="Original filename")
    user_id: Optional[UUID] = Field(None, description="User ID (auto-generated if not provided)")


class JobDescriptionUploadRequest(BaseModel):
    """Request schema for job description upload."""

    text: str = Field(..., min_length=50, description="Job description text")
    title: Optional[str] = Field(None, description="Job title")
    company: Optional[str] = Field(None, description="Company name")


class AnalysisRunRequest(BaseModel):
    """Request schema for running an ATS analysis."""

    resume_id: UUID = Field(..., description="Resume ID to analyze")
    jd_id: UUID = Field(..., description="Job description ID to compare against")
    weights: Optional[Dict[str, float]] = Field(
        None,
        description="Custom scoring weights (keyword, semantic, category)",
    )


class QuizStartRequest(BaseModel):
    """Request schema for starting a skill validation quiz."""

    analysis_id: UUID = Field(..., description="Analysis ID to generate quiz for")
    skill: str = Field(..., description="Skill to test")
    difficulty: Optional[str] = Field("medium", description="Quiz difficulty: easy, medium, hard")
    num_questions: Optional[int] = Field(10, ge=1, le=10, description="Number of questions")


class QuizSubmitRequest(BaseModel):
    """Request schema for submitting quiz answers."""

    quiz_id: UUID = Field(..., description="Quiz ID")
    answers: List[Dict] = Field(..., description="List of answer objects")


class FeedbackRequest(BaseModel):
    """Request schema for submitting feedback."""

    analysis_id: UUID = Field(..., description="Analysis ID")
    feedback_type: str = Field(..., description="Type: score_adjustment, weight_change, general")
    revised_score: Optional[float] = Field(None, ge=0, le=100, description="Revised score (0-100)")
    weight_adjustments: Optional[Dict[str, float]] = Field(None, description="New weights")
    comments: Optional[str] = Field(None, description="Feedback comments")
