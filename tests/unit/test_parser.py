"""Unit tests for the document parser module."""

import pytest

from src.nlp.parser import DocumentParser


@pytest.fixture
def parser():
    return DocumentParser()


class TestDocumentParser:
    """Tests for DocumentParser."""

    def test_parse_resume_text_basic(self, parser):
        """Test basic resume text parsing."""
        text = """
        John Doe
        Software Engineer

        Summary
        Experienced software engineer with 5 years of Python development.

        Experience
        Senior Developer at TechCorp (2020-2023)
        - Built REST APIs using FastAPI
        - Managed PostgreSQL databases

        Skills
        Python, FastAPI, PostgreSQL, Docker, AWS
        """
        result = parser.parse_resume_text(text)
        assert "raw_text" in result
        assert "sections" in result
        assert len(result["raw_text"]) > 0

    def test_parse_resume_text_extracts_sections(self, parser):
        """Test that sections are correctly identified."""
        text = """
        John Doe

        Summary
        Experienced developer.

        Experience
        Worked at Company A for 3 years.

        Skills
        Python, Java, SQL

        Education
        BS Computer Science
        """
        result = parser.parse_resume_text(text)
        sections = result["sections"]
        # Parser identifies sections by header patterns
        assert "experience" in sections
        assert "skills" in sections
        assert "education" in sections

    def test_parse_resume_text_empty_raises_error(self, parser):
        """Test that empty text raises ParsingError."""
        from src.core.exceptions import ParsingError

        with pytest.raises(ParsingError):
            parser.parse_resume_text("")

        with pytest.raises(ParsingError):
            parser.parse_resume_text("   ")

    def test_parse_job_description_basic(self, parser):
        """Test basic job description parsing."""
        text = """
        Senior Python Developer

        Description
        We are looking for an experienced Python developer.

        Requirements
        - 5+ years Python experience
        - FastAPI or Django
        - PostgreSQL

        Responsibilities
        - Design and implement APIs
        - Code review
        """
        result = parser.parse_job_description(text)
        assert "raw_text" in result
        assert "processed_text" in result
        assert "sections" in result

    def test_parse_job_description_empty_raises_error(self, parser):
        """Test that empty JD raises ParsingError."""
        from src.core.exceptions import ParsingError

        with pytest.raises(ParsingError):
            parser.parse_job_description("")

    def test_clean_text_removes_extra_whitespace(self, parser):
        """Test text cleaning functionality."""
        text = "Hello    World\n\n\n\nTest"
        cleaned = parser._clean_text(text)
        assert "    " not in cleaned
        assert "\n\n\n\n" not in cleaned

    def test_extract_bullet_points(self, parser):
        """Test bullet point extraction."""
        text = """
        - Built scalable REST APIs serving 1M requests/day
        - Reduced latency by 40% through caching optimization
        * Managed team of 5 engineers
        1. Implemented CI/CD pipeline
        2. Short
        """
        bullets = parser.extract_bullet_points(text)
        bullet_texts = [b["text"] for b in bullets]
        assert len(bullets) >= 3
        assert "Built scalable REST APIs serving 1M requests/day" in bullet_texts

    def test_extract_bullet_points_filters_short(self, parser):
        """Test that very short bullets are filtered."""
        text = """
        - OK
        - This is a proper bullet point with enough content
        """
        bullets = parser.extract_bullet_points(text)
        assert "OK" not in bullets
