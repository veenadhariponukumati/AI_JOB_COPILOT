"""Unit tests for ATS explanation evidence consistency."""

from src.matching.explainer import ExplainabilityEngine


def test_compile_evidence_uses_matched_skill_evidence():
    explainer = ExplainabilityEngine()
    matched_skills = [
        {
            "skill": "APIs",
            "matched_by": "semantic",
            "match_reason": "REST APIs satisfy APIs.",
            "evidence_from_resume": "Built REST APIs for backend services.",
            "confidence": 0.91,
        }
    ]

    evidence = explainer._compile_evidence({}, matched_skills, "")

    assert evidence == [
        {
            "skill": "APIs",
            "found_in_resume": True,
            "similarity": 0.91,
            "evidence_snippets": ["Built REST APIs for backend services."],
            "matched_by": "semantic",
            "match_reason": "REST APIs satisfy APIs.",
        }
    ]


def test_compile_evidence_does_not_emit_not_found_for_matched_skill():
    explainer = ExplainabilityEngine()
    matched_skills = [
        {
            "skill": "System Design",
            "matched_by": "exact",
            "match_reason": "Exact skill name match.",
            "evidence_from_resume": "System Design",
            "confidence": 1.0,
        }
    ]

    evidence = explainer._compile_evidence(
        {"System Design": {"has_evidence": False, "resume_evidence": []}},
        matched_skills,
        "",
    )

    assert evidence
    assert all(item["found_in_resume"] for item in evidence)
