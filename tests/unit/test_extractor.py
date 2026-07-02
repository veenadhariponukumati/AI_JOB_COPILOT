"""Unit tests for the skill extraction module."""

import pytest
from src.nlp.extractor import (
    SkillExtractor,
    EXTRACTION_PROMPT,
    GENERIC_WORD_BLOCKLIST,
    MIN_SKILL_LENGTH,
    MAX_SKILL_LENGTH,
)


@pytest.fixture
def extractor():
    return SkillExtractor()


class TestSkillExtractor:
    """Tests for SkillExtractor validation logic."""

    def test_normalize_skill_name(self, extractor):
        """Test skill name normalization."""
        assert extractor.normalize_skill_name("Python") == "python"
        assert extractor.normalize_skill_name("React.js") == "reactjs"
        assert extractor.normalize_skill_name("Machine Learning") == "machinelearning"
        assert extractor.normalize_skill_name("  Docker  ") == "docker"

    def test_validate_skills_blocks_generic_words(self, extractor):
        """Test that generic words are filtered out."""
        raw_skills = [
            {"name": "team", "category": "behavioral", "confidence": 0.9, "evidence": ""},
            {"name": "Python", "category": "technical", "confidence": 0.95, "evidence": ""},
            {"name": "good", "category": "behavioral", "confidence": 0.8, "evidence": ""},
        ]
        validated = extractor._validate_skills(raw_skills)
        skill_names = [s["name"] for s in validated]
        assert "team" not in skill_names
        assert "good" not in skill_names
        assert "Python" in skill_names

    def test_validate_skills_enforces_length(self, extractor):
        """Test minimum and maximum length enforcement."""
        raw_skills = [
            {"name": "A", "category": "technical", "confidence": 0.9, "evidence": ""},
            {"name": "Python", "category": "technical", "confidence": 0.9, "evidence": ""},
            {"name": "X" * 100, "category": "technical", "confidence": 0.9, "evidence": ""},
        ]
        validated = extractor._validate_skills(raw_skills)
        assert len(validated) == 1
        assert validated[0]["name"] == "Python"

    def test_validate_skills_enforces_confidence_threshold(self, extractor):
        """Test confidence threshold filtering."""
        raw_skills = [
            {"name": "Python", "category": "technical", "confidence": 0.9, "evidence": ""},
            {"name": "Django", "category": "technical", "confidence": 0.3, "evidence": ""},
        ]
        validated = extractor._validate_skills(raw_skills)
        skill_names = [s["name"] for s in validated]
        assert "Python" in skill_names
        assert "Django" not in skill_names

    def test_validate_skills_deduplicates(self, extractor):
        """Test deduplication by normalized name."""
        raw_skills = [
            {"name": "Python", "category": "technical", "confidence": 0.9, "evidence": ""},
            {"name": "python", "category": "technical", "confidence": 0.85, "evidence": ""},
            {"name": "PYTHON", "category": "technical", "confidence": 0.8, "evidence": ""},
        ]
        validated = extractor._validate_skills(raw_skills)
        assert len(validated) == 1

    def test_validate_skills_requires_letters(self, extractor):
        """Test that skills must contain at least one letter."""
        raw_skills = [
            {"name": "123", "category": "technical", "confidence": 0.9, "evidence": ""},
            {"name": "C++", "category": "technical", "confidence": 0.9, "evidence": ""},
        ]
        validated = extractor._validate_skills(raw_skills)
        skill_names = [s["name"] for s in validated]
        assert "123" not in skill_names
        assert "C++" in skill_names

    def test_blocklist_contains_common_generic_words(self):
        """Verify blocklist includes common generic words."""
        assert "team" in GENERIC_WORD_BLOCKLIST
        assert "work" in GENERIC_WORD_BLOCKLIST
        assert "experience" in GENERIC_WORD_BLOCKLIST
        assert "detail-oriented" in GENERIC_WORD_BLOCKLIST

    def test_validated_skill_structure(self, extractor):
        """Test that validated skills have correct structure."""
        raw_skills = [
            {"name": "FastAPI", "category": "technical", "confidence": 0.9, "evidence": "Used FastAPI"},
        ]
        validated = extractor._validate_skills(raw_skills)
        assert len(validated) == 1
        skill = validated[0]
        assert "name" in skill
        assert "normalized_name" in skill
        assert "category" in skill
        assert "confidence" in skill
        assert "evidence" in skill
        assert skill["normalized_name"] == "fastapi"

    def test_prompt_preserves_llm_application_concepts(self):
        """Extractor prompt should not collapse concrete LLM app skills into ML."""
        for concept in [
            "LLM Application Patterns",
            "RAG",
            "Orchestration",
            "Function Calling",
            "AI Assistant Integration",
        ]:
            assert concept in EXTRACTION_PROMPT
        assert "Do not collapse these into generic Machine Learning" in EXTRACTION_PROMPT
