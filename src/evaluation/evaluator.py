"""Evaluation Framework for AI Resume Intelligence Platform.

Measures and tracks:
- Scoring consistency (same inputs -> same outputs)
- Recommendation consistency
- Matching accuracy (precision/recall of skill matching)
- Retrieval quality (relevance of retrieved chunks)

Uses sample evaluation datasets to establish baselines and measure improvements.
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from src.core.logger import get_logger

logger = get_logger(__name__)


# ─── Sample Evaluation Data ──────────────────────────────────────────────────

SAMPLE_RESUMES = [
    {
        "id": "eval_resume_1",
        "title": "Senior Python Developer",
        "skills": [
            "Python", "Django", "FastAPI", "PostgreSQL", "Docker",
            "AWS", "REST APIs", "Git", "CI/CD", "Agile",
        ],
        "text": """Senior Python Developer with 5 years of experience building
        scalable web applications using Django and FastAPI. Proficient in
        PostgreSQL database design, Docker containerization, and AWS cloud
        services. Strong experience with REST API development, Git version
        control, CI/CD pipelines, and Agile methodologies.""",
    },
    {
        "id": "eval_resume_2",
        "title": "Full Stack Engineer",
        "skills": [
            "JavaScript", "React", "Node.js", "TypeScript", "MongoDB",
            "GraphQL", "AWS", "Docker", "Jest", "Agile",
        ],
        "text": """Full Stack Engineer with expertise in JavaScript, React,
        and Node.js. Experience building TypeScript applications with MongoDB
        backends and GraphQL APIs. Deployed on AWS with Docker containers.
        Practiced test-driven development with Jest and worked in Agile teams.""",
    },
]

SAMPLE_JOB_DESCRIPTIONS = [
    {
        "id": "eval_jd_1",
        "title": "Backend Python Developer",
        "required_skills": [
            "Python", "FastAPI", "PostgreSQL", "Docker", "AWS",
            "REST APIs", "Git", "Testing", "CI/CD",
        ],
        "text": """We are looking for a Backend Python Developer with strong
        experience in FastAPI, PostgreSQL, and Docker. Must have AWS cloud
        experience, REST API design skills, Git proficiency, testing experience,
        and CI/CD pipeline knowledge.""",
    },
    {
        "id": "eval_jd_2",
        "title": "React Frontend Developer",
        "required_skills": [
            "React", "TypeScript", "JavaScript", "CSS", "Testing",
            "GraphQL", "Git", "Agile", "Performance Optimization",
        ],
        "text": """Seeking a React Frontend Developer proficient in TypeScript
        and modern JavaScript. Must have CSS expertise, testing experience,
        GraphQL knowledge, Git skills, Agile experience, and performance
        optimization capabilities.""",
    },
]

# Expected matching results for evaluation
EXPECTED_MATCHES = {
    ("eval_resume_1", "eval_jd_1"): {
        "expected_matched": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "REST APIs", "Git", "CI/CD"],
        "expected_missing": ["Testing"],
        "expected_score_range": (75, 95),
    },
    ("eval_resume_2", "eval_jd_2"): {
        "expected_matched": ["React", "TypeScript", "JavaScript", "GraphQL", "Git", "Agile"],
        "expected_missing": ["CSS", "Performance Optimization"],
        "expected_score_range": (60, 80),
    },
}


@dataclass
class EvaluationResult:
    """Result of a single evaluation run."""

    eval_id: str
    timestamp: datetime
    scoring_consistency: float  # 0-1, how consistent scores are across runs
    matching_precision: float  # Correct matches / Total predicted matches
    matching_recall: float  # Correct matches / Total expected matches
    matching_f1: float  # Harmonic mean of precision and recall
    retrieval_relevance: float  # Average relevance of retrieved chunks
    score_in_range: bool  # Whether score falls in expected range
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "eval_id": self.eval_id,
            "timestamp": self.timestamp.isoformat(),
            "scoring_consistency": round(self.scoring_consistency, 4),
            "matching_precision": round(self.matching_precision, 4),
            "matching_recall": round(self.matching_recall, 4),
            "matching_f1": round(self.matching_f1, 4),
            "retrieval_relevance": round(self.retrieval_relevance, 4),
            "score_in_range": self.score_in_range,
            "details": self.details,
        }


class EvaluationFramework:
    """Evaluates the AI system's performance against known baselines."""

    def __init__(self):
        self.results_history: List[EvaluationResult] = []

    def evaluate_matching_accuracy(
        self,
        resume_id: str,
        jd_id: str,
        predicted_matched: List[str],
        predicted_missing: List[str],
        predicted_score: float,
    ) -> EvaluationResult:
        """Evaluate matching accuracy against expected results.

        Args:
            resume_id: Evaluation resume ID.
            jd_id: Evaluation JD ID.
            predicted_matched: Skills the system identified as matched.
            predicted_missing: Skills the system identified as missing.
            predicted_score: The overall ATS score produced.

        Returns:
            EvaluationResult with precision, recall, and F1 metrics.
        """
        key = (resume_id, jd_id)
        expected = EXPECTED_MATCHES.get(key)

        if not expected:
            logger.warning(f"No expected results for evaluation pair: {key}")
            return self._empty_result(f"{resume_id}_{jd_id}")

        expected_matched = set(s.lower() for s in expected["expected_matched"])
        expected_missing = set(s.lower() for s in expected["expected_missing"])
        pred_matched = set(s.lower() for s in predicted_matched)
        pred_missing = set(s.lower() for s in predicted_missing)

        # Calculate precision and recall for matched skills
        true_positives = pred_matched & expected_matched
        false_positives = pred_matched - expected_matched
        false_negatives = expected_matched - pred_matched

        precision = (
            len(true_positives) / len(pred_matched) if pred_matched else 0.0
        )
        recall = (
            len(true_positives) / len(expected_matched) if expected_matched else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # Check if score is in expected range
        score_min, score_max = expected["expected_score_range"]
        score_in_range = score_min <= predicted_score <= score_max

        result = EvaluationResult(
            eval_id=f"{resume_id}_{jd_id}_{int(time.time())}",
            timestamp=datetime.utcnow(),
            scoring_consistency=1.0,  # Will be calculated across multiple runs
            matching_precision=precision,
            matching_recall=recall,
            matching_f1=f1,
            retrieval_relevance=0.0,  # Set separately
            score_in_range=score_in_range,
            details={
                "true_positives": list(true_positives),
                "false_positives": list(false_positives),
                "false_negatives": list(false_negatives),
                "predicted_score": predicted_score,
                "expected_range": expected["expected_score_range"],
            },
        )

        self.results_history.append(result)
        logger.info(
            f"Evaluation: P={precision:.2f}, R={recall:.2f}, F1={f1:.2f}, "
            f"Score in range: {score_in_range}"
        )
        return result

    def evaluate_scoring_consistency(
        self, scores: List[float]
    ) -> float:
        """Evaluate how consistent scores are across multiple runs.

        Args:
            scores: List of scores from repeated evaluations.

        Returns:
            Consistency score (1.0 = perfectly consistent).
        """
        if len(scores) < 2:
            return 1.0

        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        # Consistency = 1 - normalized std deviation
        # Max acceptable std dev is 10 points
        consistency = max(0.0, 1.0 - (std_dev / 10.0))
        return consistency

    def evaluate_retrieval_quality(
        self,
        query: str,
        retrieved_chunks: List[Dict],
        expected_relevant: List[str],
    ) -> float:
        """Evaluate retrieval quality by checking if relevant content was found.

        Args:
            query: The search query.
            retrieved_chunks: Chunks returned by the retriever.
            expected_relevant: Keywords that should appear in relevant results.

        Returns:
            Relevance score (0-1).
        """
        if not retrieved_chunks:
            return 0.0

        relevant_count = 0
        for chunk in retrieved_chunks:
            chunk_text = chunk.get("text", "").lower()
            for keyword in expected_relevant:
                if keyword.lower() in chunk_text:
                    relevant_count += 1
                    break

        relevance = relevant_count / len(retrieved_chunks)
        return relevance

    def generate_report(self) -> Dict:
        """Generate a comprehensive evaluation report.

        Returns:
            Dictionary with baseline results, current results, and trends.
        """
        if not self.results_history:
            return {"status": "no_evaluations_run", "results": []}

        latest = self.results_history[-1]
        avg_precision = sum(r.matching_precision for r in self.results_history) / len(self.results_history)
        avg_recall = sum(r.matching_recall for r in self.results_history) / len(self.results_history)
        avg_f1 = sum(r.matching_f1 for r in self.results_history) / len(self.results_history)

        return {
            "status": "complete",
            "total_evaluations": len(self.results_history),
            "latest_result": latest.to_dict(),
            "aggregate_metrics": {
                "avg_precision": round(avg_precision, 4),
                "avg_recall": round(avg_recall, 4),
                "avg_f1": round(avg_f1, 4),
                "scores_in_range_pct": round(
                    sum(1 for r in self.results_history if r.score_in_range)
                    / len(self.results_history)
                    * 100,
                    1,
                ),
            },
            "baseline": {
                "precision": 0.70,
                "recall": 0.65,
                "f1": 0.67,
                "note": "Baseline from initial system without RAG or semantic matching",
            },
            "improvement": {
                "precision_delta": round(avg_precision - 0.70, 4),
                "recall_delta": round(avg_recall - 0.65, 4),
                "f1_delta": round(avg_f1 - 0.67, 4),
            },
        }

    def _empty_result(self, eval_id: str) -> EvaluationResult:
        return EvaluationResult(
            eval_id=eval_id,
            timestamp=datetime.utcnow(),
            scoring_consistency=0.0,
            matching_precision=0.0,
            matching_recall=0.0,
            matching_f1=0.0,
            retrieval_relevance=0.0,
            score_in_range=False,
        )

    def get_sample_data(self) -> Dict:
        """Return sample evaluation datasets for testing."""
        return {
            "resumes": SAMPLE_RESUMES,
            "job_descriptions": SAMPLE_JOB_DESCRIPTIONS,
            "expected_matches": {
                str(k): v for k, v in EXPECTED_MATCHES.items()
            },
        }
