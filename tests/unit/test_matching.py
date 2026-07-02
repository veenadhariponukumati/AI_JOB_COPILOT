"""Unit tests for the hybrid matching engine."""

import pytest
from src.matching.engine import HybridMatchingEngine


@pytest.fixture
def engine():
    return HybridMatchingEngine(
        keyword_weight=0.4,
        semantic_weight=0.4,
        category_weight=0.2,
    )


class TestHybridMatchingEngine:
    """Tests for HybridMatchingEngine."""

    def test_keyword_match_exact(self, engine):
        """Test exact keyword matching."""
        resume_skills = [
            {"name": "Python", "normalized_name": "python", "category": "technical"},
            {"name": "FastAPI", "normalized_name": "fastapi", "category": "technical"},
        ]
        jd_skills = [
            {"name": "Python", "normalized_name": "python", "category": "technical"},
            {"name": "FastAPI", "normalized_name": "fastapi", "category": "technical"},
            {"name": "Docker", "normalized_name": "docker", "category": "technical"},
        ]
        result = engine._keyword_match(resume_skills, jd_skills)
        assert result["total_matched"] == 2
        assert result["score"] == pytest.approx(2 / 3, rel=0.01)
        assert "Docker" in result["unmatched"]

    def test_keyword_match_synonym(self, engine):
        """Test synonym matching (e.g., JS -> JavaScript)."""
        resume_skills = [
            {"name": "JavaScript", "normalized_name": "javascript", "category": "technical"},
        ]
        jd_skills = [
            {"name": "JS", "normalized_name": "js", "category": "technical"},
        ]
        result = engine._keyword_match(resume_skills, jd_skills)
        assert result["total_matched"] >= 1
        assert len(result["synonym_matches"]) >= 1

    def test_keyword_match_empty_jd(self, engine):
        """Test with empty JD skills."""
        resume_skills = [
            {"name": "Python", "normalized_name": "python", "category": "technical"},
        ]
        result = engine._keyword_match(resume_skills, [])
        assert result["score"] == 0.0

    def test_semantic_match_with_evidence(self, engine):
        """Test semantic matching with evidence."""
        jd_skills = [
            {"name": "Python", "category": "technical"},
            {"name": "Docker", "category": "technical"},
        ]
        semantic_evidence = {
            "Python": {"has_evidence": True, "max_similarity": 0.92, "resume_evidence": [{"text": "Python dev"}]},
            "Docker": {"has_evidence": False, "max_similarity": 0.0, "resume_evidence": []},
        }
        result = engine._semantic_match(jd_skills, semantic_evidence)
        assert result["coverage"] == 0.5
        assert result["avg_similarity"] > 0.0
        assert len(result["matches"]) == 1

    def test_calculate_score_full(self, engine):
        """Test full score calculation."""
        resume_skills = [
            {"name": "Python", "normalized_name": "python", "category": "technical"},
            {"name": "FastAPI", "normalized_name": "fastapi", "category": "technical"},
        ]
        jd_skills = [
            {"name": "Python", "normalized_name": "python", "category": "core"},
            {"name": "FastAPI", "normalized_name": "fastapi", "category": "technical"},
            {"name": "Docker", "normalized_name": "docker", "category": "supporting"},
        ]
        semantic_evidence = {
            "Python": {"has_evidence": True, "max_similarity": 0.95, "resume_evidence": [{"text": "Python"}]},
            "FastAPI": {"has_evidence": True, "max_similarity": 0.88, "resume_evidence": [{"text": "FastAPI"}]},
            "Docker": {"has_evidence": False, "max_similarity": 0.0, "resume_evidence": []},
        }

        result = engine.calculate_score(resume_skills, jd_skills, semantic_evidence)

        assert "overall_score" in result
        assert "keyword_score" in result
        assert "semantic_score" in result
        assert "matched_skills" in result
        assert "missing_skills" in result
        assert result["overall_score"] > 0
        assert result["overall_score"] <= 100
        assert len(result["missing_skills"]) >= 1

    def test_get_missing_skills(self, engine):
        """Test missing skills identification."""
        jd_skills = [
            {"name": "Python", "category": "core"},
            {"name": "Docker", "category": "supporting"},
        ]
        matched_skills = [{"skill": "Python", "match_type": "exact"}]

        missing = engine._get_missing_skills(jd_skills, matched_skills)
        assert len(missing) == 1
        assert missing[0]["skill"] == "Docker"

    def test_phrase_match(self, engine):
        """Test partial/phrase matching."""
        resume_skills = {"nodejs", "machine learning"}
        result = engine._phrase_match("node", resume_skills)
        assert result == "nodejs"

    def test_phrase_match_rejects_false_equivalence(self, engine):
        """React and React Native are different skills - must never phrase-match."""
        resume_skills = {"react native", "machine learning"}
        result = engine._phrase_match("react", resume_skills)
        assert result is None

    def test_phrase_match_avoids_short(self, engine):
        """Test that short strings don't trigger phrase match."""
        resume_skills = {"api", "sql"}
        result = engine._phrase_match("ap", resume_skills)
        assert result is None

    def test_weights_sum_correctly(self, engine):
        """Test that weights are applied correctly."""
        assert engine.keyword_weight + engine.semantic_weight + engine.category_weight == pytest.approx(1.0)

    def test_rest_apis_matches_apis_with_evidence(self, engine):
        resume_skills = [
            {"name": "REST APIs", "normalized_name": "restapis", "category": "technical", "evidence": "Built REST APIs"}
        ]
        jd_skills = [{"name": "APIs", "normalized_name": "apis", "category": "technical"}]
        canonical_groups = [
            {
                "canonical_skill": "APIs",
                "original_resume_terms": ["REST APIs"],
                "original_jd_terms": ["APIs"],
                "category": "technical",
                "confidence": 0.91,
                "evidence_from_resume": "Built REST APIs",
                "evidence_from_jd": "APIs",
                "match_reason": "REST APIs are a concrete API implementation skill.",
            }
        ]

        result = engine.calculate_score(resume_skills, jd_skills, {}, canonical_groups=canonical_groups)

        assert result["matched_skills"][0]["skill"] == "APIs"
        assert result["matched_skills"][0]["matched_by"] in {"normalized", "semantic"}
        assert result["matched_skills"][0]["evidence_from_resume"]
        assert result["missing_skills"] == []

    def test_spec_driven_matches_writing_specifications(self, engine):
        resume_skills = [
            {
                "name": "Spec-Driven Development",
                "normalized_name": "specdrivendevelopment",
                "category": "functional",
                "evidence": "Spec-Driven Development workflows",
            }
        ]
        jd_skills = [{"name": "Writing Specifications", "normalized_name": "writingspecifications", "category": "functional"}]
        canonical_groups = [
            {
                "canonical_skill": "Specification Writing",
                "original_resume_terms": ["Spec-Driven Development"],
                "original_jd_terms": ["Writing Specifications"],
                "category": "functional",
                "confidence": 0.88,
                "evidence_from_resume": "Spec-Driven Development workflows",
                "evidence_from_jd": "Writing Specifications",
                "match_reason": "Spec-driven development requires writing specifications.",
            }
        ]

        result = engine.calculate_score(resume_skills, jd_skills, {}, canonical_groups=canonical_groups)

        assert result["matched_skills"][0]["matched_by"] == "semantic"
        assert result["matched_skills"][0]["evidence_from_resume"]

    def test_ai_augmented_tools_matches_ai_coding_tools(self, engine):
        resume_skills = [
            {
                "name": "AI-Augmented Development Tools",
                "normalized_name": "aiaugmenteddevelopmenttools",
                "category": "technical",
                "evidence": "AI-Augmented Development Tools",
            }
        ]
        jd_skills = [{"name": "AI Coding Tools", "normalized_name": "aicodingtools", "category": "technical"}]
        canonical_groups = [
            {
                "canonical_skill": "AI Coding Tools",
                "original_resume_terms": ["AI-Augmented Development Tools"],
                "original_jd_terms": ["AI Coding Tools"],
                "category": "technical",
                "confidence": 0.9,
                "evidence_from_resume": "AI-Augmented Development Tools",
                "evidence_from_jd": "AI Coding Tools",
                "match_reason": "AI-augmented development tools are AI coding tools.",
            }
        ]

        result = engine.calculate_score(resume_skills, jd_skills, {}, canonical_groups=canonical_groups)

        assert result["matched_skills"][0]["matched_by"] == "semantic"
        assert result["matched_skills"][0]["evidence_from_resume"]

    def test_cicd_matches_through_deterministic_normalization(self, engine):
        resume_skills = [
            {"name": "CI/CD", "normalized_name": "cicd", "category": "technical", "evidence": "CI/CD pipelines"}
        ]
        jd_skills = [{"name": "cicd", "normalized_name": "cicd", "category": "technical"}]

        result = engine.calculate_score(resume_skills, jd_skills, {})

        assert result["matched_skills"][0]["matched_by"] == "normalized"
        assert result["missing_skills"] == []

    def test_backend_language_alternative_group(self, engine):
        resume_skills = [
            {"name": "Python", "normalized_name": "python", "category": "technical", "evidence": "Python"},
            {"name": "TypeScript", "normalized_name": "typescript", "category": "technical", "evidence": "TypeScript"},
        ]
        jd_skills = [
            {"name": "Python", "normalized_name": "python", "category": "technical"},
            {"name": "Java", "normalized_name": "java", "category": "technical"},
            {"name": "Go", "normalized_name": "go", "category": "technical"},
            {"name": "TypeScript", "normalized_name": "typescript", "category": "technical"},
        ]
        alternative_groups = [
            {
                "canonical_skill": "Java OR Go OR TypeScript",
                "options": ["Java", "Go", "TypeScript"],
                "category": "technical",
                "evidence_from_jd": "Java OR Go OR TypeScript",
            }
        ]

        result = engine.calculate_score(
            resume_skills,
            jd_skills,
            {},
            alternative_groups=alternative_groups,
        )
        missing_names = {skill["skill"] for skill in result["missing_skills"]}

        assert "Java" not in missing_names
        assert "Go" not in missing_names
        assert any(m["matched_by"] == "alternative_group" for m in result["matched_skills"])

    def test_system_design_and_production_operations_exact(self, engine):
        resume_skills = [
            {"name": "System Design", "normalized_name": "systemdesign", "category": "technical", "evidence": "System Design"},
            {
                "name": "Production Operations",
                "normalized_name": "productionoperations",
                "category": "technical",
                "evidence": "Production Operations",
            },
        ]
        jd_skills = [
            {"name": "System Design", "normalized_name": "systemdesign", "category": "technical"},
            {"name": "Production Operations", "normalized_name": "productionoperations", "category": "technical"},
        ]

        result = engine.calculate_score(resume_skills, jd_skills, {})

        assert len(result["matched_skills"]) == 2
        assert result["missing_skills"] == []
        assert all(match["evidence_from_resume"] for match in result["matched_skills"])

    def test_matched_skills_have_evidence_and_do_not_overlap_missing(self, engine):
        resume_skills = [{"name": "Python", "normalized_name": "python", "category": "technical", "evidence": "Python"}]
        jd_skills = [{"name": "Python", "normalized_name": "python", "category": "technical"}]

        result = engine.calculate_score(resume_skills, jd_skills, {})

        matched = {skill["skill"] for skill in result["matched_skills"]}
        missing = {skill["skill"] for skill in result["missing_skills"]}
        assert matched.isdisjoint(missing)
        assert all(skill["evidence_from_resume"] for skill in result["matched_skills"])
        assert result["telemetry"]["exact"] == 1

    def test_semantic_match_requires_confidence_and_evidence(self, engine):
        resume_skills = [
            {
                "name": "RAG Pipelines",
                "normalized_name": "ragpipelines",
                "category": "technical",
                "evidence": "RAG Pipelines",
            }
        ]
        jd_skills = [
            {
                "name": "LLM Application Patterns",
                "normalized_name": "llmapplicationpatterns",
                "category": "technical",
            }
        ]
        canonical_groups = [
            {
                "canonical_skill": "LLM Application Patterns",
                "original_resume_terms": ["RAG Pipelines"],
                "original_jd_terms": ["LLM Application Patterns"],
                "category": "technical",
                "confidence": 0.79,
                "evidence_from_resume": "RAG Pipelines",
                "match_reason": "Below threshold.",
            },
            {
                "canonical_skill": "LLM Application Patterns",
                "original_resume_terms": ["RAG Pipelines"],
                "original_jd_terms": ["LLM Application Patterns"],
                "category": "technical",
                "confidence": 0.95,
                "evidence_from_resume": "",
                "match_reason": "No evidence.",
            },
        ]

        result = engine.calculate_score(resume_skills, jd_skills, {}, canonical_groups=canonical_groups)

        assert result["matched_skills"] == []
        assert result["missing_skills"][0]["skill"] == "LLM Application Patterns"

    def test_semantic_match_rejects_negated_placeholder_evidence(self, engine):
        resume_skills = [
            {
                "name": "Backend Services",
                "normalized_name": "backendservices",
                "category": "technical",
                "evidence": "Backend services",
            }
        ]
        jd_skills = [{"name": "Microservices", "normalized_name": "microservices", "category": "technical"}]
        canonical_groups = [
            {
                "canonical_skill": "Microservices",
                "original_resume_terms": ["Backend Services"],
                "original_jd_terms": ["Microservices"],
                "category": "technical",
                "confidence": 0.91,
                "evidence_from_resume": "No direct mention of microservices.",
                "match_reason": "Backend services are related.",
            }
        ]

        result = engine.calculate_score(resume_skills, jd_skills, {}, canonical_groups=canonical_groups)

        assert result["matched_skills"] == []
        assert result["missing_skills"][0]["skill"] == "Microservices"

    def test_semantic_match_rejects_untraceable_evidence(self, engine):
        resume_skills = [
            {
                "name": "Vector Search",
                "normalized_name": "vectorsearch",
                "category": "technical",
                "evidence": "Built vector search indexes",
            }
        ]
        jd_skills = [
            {
                "name": "LLM Application Patterns",
                "normalized_name": "llmapplicationpatterns",
                "category": "technical",
            }
        ]
        canonical_groups = [
            {
                "canonical_skill": "LLM Application Patterns",
                "original_resume_terms": ["Generative AI Systems"],
                "original_jd_terms": ["LLM Application Patterns"],
                "category": "technical",
                "confidence": 0.91,
                "evidence_from_resume": "Designed unrelated analytics workflows",
                "match_reason": "LLM application patterns are related to AI systems.",
            }
        ]

        result = engine.calculate_score(resume_skills, jd_skills, {}, canonical_groups=canonical_groups)

        assert result["matched_skills"] == []
        assert result["missing_skills"][0]["skill"] == "LLM Application Patterns"

    def test_missing_skills_compare_resume_skill_keys(self, engine):
        jd_skills = [{"name": "TypeScript", "category": "technical"}]
        matched_skills = [
            {
                "skill": "Java OR Go OR TypeScript",
                "canonical_skill": "Backend Language",
                "resume_skill": "TypeScript",
                "matched_by": "alternative_group",
            }
        ]

        assert engine._get_missing_skills(jd_skills, matched_skills) == []
