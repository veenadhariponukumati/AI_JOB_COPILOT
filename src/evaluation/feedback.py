"""Feedback Loop System.

Implements iterative improvement through:
- Recruiter feedback collection
- Scoring adjustments
- Weight adjustments
- Historical revision tracking
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.database.models import AnalysisFeedback, ATSAnalysis

logger = get_logger(__name__)


class FeedbackManager:
    """Manages the feedback loop for continuous improvement."""

    def __init__(self, db: Session):
        self.db = db

    def submit_score_adjustment(
        self,
        analysis_id: UUID,
        revised_score: float,
        comments: Optional[str] = None,
    ) -> Dict:
        """Submit a score adjustment from recruiter feedback.

        Args:
            analysis_id: The analysis being adjusted.
            revised_score: The corrected score.
            comments: Optional explanation.

        Returns:
            Feedback record details.
        """
        # Get original analysis
        analysis = self.db.query(ATSAnalysis).filter(
            ATSAnalysis.analysis_id == analysis_id
        ).first()

        if not analysis:
            return {"error": "Analysis not found"}

        original_score = analysis.overall_score

        # Create feedback record
        feedback = AnalysisFeedback(
            analysis_id=analysis_id,
            feedback_type="score_adjustment",
            original_score=original_score,
            revised_score=revised_score,
            comments=comments,
        )
        self.db.add(feedback)
        self.db.commit()

        logger.info(
            f"Score adjustment: {original_score} -> {revised_score} "
            f"(analysis: {analysis_id})"
        )

        return {
            "feedback_id": str(feedback.feedback_id),
            "original_score": original_score,
            "revised_score": revised_score,
            "delta": revised_score - (original_score or 0),
            "comments": comments,
        }

    def submit_weight_adjustment(
        self,
        analysis_id: UUID,
        weight_adjustments: Dict[str, float],
        comments: Optional[str] = None,
    ) -> Dict:
        """Submit weight adjustments for scoring categories.

        Args:
            analysis_id: The analysis context.
            weight_adjustments: New weights (e.g., {"keyword": 0.5, "semantic": 0.3}).
            comments: Explanation for the adjustment.

        Returns:
            Feedback record details.
        """
        # Validate weights sum to 1.0
        total = sum(weight_adjustments.values())
        if abs(total - 1.0) > 0.01:
            return {"error": f"Weights must sum to 1.0, got {total}"}

        feedback = AnalysisFeedback(
            analysis_id=analysis_id,
            feedback_type="weight_change",
            weight_adjustments=weight_adjustments,
            comments=comments,
        )
        self.db.add(feedback)
        self.db.commit()

        logger.info(f"Weight adjustment submitted: {weight_adjustments}")

        return {
            "feedback_id": str(feedback.feedback_id),
            "weight_adjustments": weight_adjustments,
            "comments": comments,
        }

    def submit_general_feedback(
        self,
        analysis_id: UUID,
        comments: str,
    ) -> Dict:
        """Submit general recruiter feedback.

        Args:
            analysis_id: The analysis being reviewed.
            comments: Feedback text.

        Returns:
            Feedback record details.
        """
        feedback = AnalysisFeedback(
            analysis_id=analysis_id,
            feedback_type="general",
            comments=comments,
        )
        self.db.add(feedback)
        self.db.commit()

        return {
            "feedback_id": str(feedback.feedback_id),
            "feedback_type": "general",
            "comments": comments,
        }

    def get_feedback_history(
        self, analysis_id: Optional[UUID] = None, limit: int = 50
    ) -> List[Dict]:
        """Retrieve feedback history.

        Args:
            analysis_id: Filter to specific analysis (optional).
            limit: Maximum records to return.

        Returns:
            List of feedback records.
        """
        query = self.db.query(AnalysisFeedback)
        if analysis_id:
            query = query.filter(AnalysisFeedback.analysis_id == analysis_id)
        query = query.order_by(AnalysisFeedback.created_at.desc()).limit(limit)

        records = query.all()
        return [
            {
                "feedback_id": str(r.feedback_id),
                "analysis_id": str(r.analysis_id),
                "feedback_type": r.feedback_type,
                "original_score": r.original_score,
                "revised_score": r.revised_score,
                "weight_adjustments": r.weight_adjustments,
                "comments": r.comments,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

    def get_score_revision_history(self, analysis_id: UUID) -> Dict:
        """Get the complete score revision history for an analysis.

        Returns:
            Timeline of score changes.
        """
        feedbacks = (
            self.db.query(AnalysisFeedback)
            .filter(
                AnalysisFeedback.analysis_id == analysis_id,
                AnalysisFeedback.feedback_type == "score_adjustment",
            )
            .order_by(AnalysisFeedback.created_at.asc())
            .all()
        )

        revisions = []
        for f in feedbacks:
            revisions.append(
                {
                    "timestamp": f.created_at.isoformat() if f.created_at else None,
                    "original_score": f.original_score,
                    "revised_score": f.revised_score,
                    "comments": f.comments,
                }
            )

        return {
            "analysis_id": str(analysis_id),
            "total_revisions": len(revisions),
            "revisions": revisions,
        }

    def calculate_adjustment_trends(self) -> Dict:
        """Analyze feedback trends to identify systematic biases.

        Returns:
            Trend analysis showing if scores are consistently over/under-estimated.
        """
        adjustments = (
            self.db.query(AnalysisFeedback)
            .filter(AnalysisFeedback.feedback_type == "score_adjustment")
            .all()
        )

        if not adjustments:
            return {"status": "no_adjustments", "trend": "neutral"}

        deltas = []
        for a in adjustments:
            if a.original_score is not None and a.revised_score is not None:
                deltas.append(a.revised_score - a.original_score)

        if not deltas:
            return {"status": "no_valid_adjustments", "trend": "neutral"}

        avg_delta = sum(deltas) / len(deltas)
        trend = "overscoring" if avg_delta < -2 else "underscoring" if avg_delta > 2 else "neutral"

        return {
            "total_adjustments": len(deltas),
            "avg_delta": round(avg_delta, 2),
            "trend": trend,
            "recommendation": (
                "Consider reducing base scores"
                if trend == "overscoring"
                else "Consider increasing base scores"
                if trend == "underscoring"
                else "Scoring appears well-calibrated"
            ),
        }
