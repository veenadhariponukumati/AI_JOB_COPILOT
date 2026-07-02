"""Document parsing module for resumes and job descriptions.

Handles PDF extraction, text cleaning, and section identification.
"""

import re
import tempfile
from typing import Dict, List, Optional
from pathlib import Path

from src.core.logger import get_logger
from src.core.exceptions import ParsingError

logger = get_logger(__name__)

# ─── Section Headers ─────────────────────────────────────────────────────────

RESUME_SECTION_PATTERNS = {
    "contact": (
        r"(?i)^(contact(\s*(info(rmation)?|details|me))?|personal\s*info(rmation)?|"
        r"get\s*in\s*touch|reach\s*me)\s*:?\s*$"
    ),
    "summary": (
        r"(?i)^(summary|professional\s*summary|career\s*summary|executive\s*summary|"
        r"objective|career\s*objective|professional\s*objective|profile|"
        r"professional\s*profile|career\s*profile|about\s*me|overview|"
        r"who\s*i\s*am|introduction)\s*:?\s*$"
    ),
    "experience": (
        r"(?i)^(experience|professional\s*experience|work\s*experience|"
        r"technical\s*experience|industry\s*experience|relevant\s*experience|"
        r"employment(\s*history)?|work\s*history|career\s*history|"
        r"job\s*history|professional\s*background|background|"
        r"internship(s)?(\s*experience)?|freelance(\s*work|\s*experience)?|"
        r"consulting(\s*experience)?|positions?\s*(held|of\s*responsibility)|"
        r"roles?\s*&?\s*responsibilities?)\s*:?\s*$"
    ),
    "education": (
        r"(?i)^(education(al)?(\s*background|\s*qualifications?|\s*history)?|"
        r"academic(\s*background|\s*history|\s*qualifications?)?|"
        r"degrees?(\s*&\s*certifications?)?|qualifications?|"
        r"schooling|university|college)\s*:?\s*$"
    ),
    "skills": (
        r"(?i)^(skills?|technical\s*skills?|core\s*skills?|key\s*skills?|"
        r"professional\s*skills?|competencies|core\s*competencies|"
        r"technical\s*competencies|expertise|areas?\s*of\s*expertise|"
        r"technologies|tech(\s*stack)?|tools?(\s*&\s*technologies)?|"
        r"programming(\s*languages?)?|languages?\s*&?\s*tools?|"
        r"technical\s*proficiencies|proficiencies|capabilities)\s*:?\s*$"
    ),
    "projects": (
        r"(?i)^(projects?|technical\s*projects?|personal\s*projects?|"
        r"side\s*projects?|academic\s*projects?|key\s*projects?|"
        r"notable\s*projects?|portfolio|selected\s*projects?|"
        r"open[\s\-]?source(\s*contributions?)?)\s*:?\s*$"
    ),
    "certifications": (
        r"(?i)^(certifications?|licenses?\s*&?\s*certifications?|"
        r"professional\s*certifications?|credentials?|"
        r"accreditations?|courses?(\s*&\s*certifications?)?)\s*:?\s*$"
    ),
    "awards": (
        r"(?i)^(awards?|honors?|achievements?|accomplishments?|"
        r"recognition|distinctions?|awards?\s*&\s*honors?|"
        r"scholarships?)\s*:?\s*$"
    ),
    "publications": (
        r"(?i)^(publications?|research|papers?|articles?|"
        r"conference\s*papers?|journals?)\s*:?\s*$"
    ),
    "volunteer": (
        r"(?i)^(volunteer(ing)?(\s*experience)?|community(\s*service)?|"
        r"extracurricular(s)?|activities|leadership(\s*experience)?)\s*:?\s*$"
    ),
    "languages": (
        r"(?i)^(languages?|spoken\s*languages?|language\s*proficiencies?)\s*:?\s*$"
    ),
}

JD_SECTION_PATTERNS = {
    "title": r"(?i)(job\s*title|position|role)",
    "description": r"(?i)(description|overview|about\s*the\s*role)",
    "responsibilities": r"(?i)(responsibilities|duties|what\s*you.ll\s*do|key\s*responsibilities)",
    "requirements": r"(?i)(requirements|qualifications|what\s*we.re\s*looking\s*for|must\s*have)",
    "preferred": r"(?i)(preferred|nice\s*to\s*have|bonus|desired)",
    "benefits": r"(?i)(benefits|perks|what\s*we\s*offer|compensation)",
}


class DocumentParser:
    """Parses resumes and job descriptions into structured sections."""

    def parse_resume_pdf(self, file_content: bytes) -> Dict[str, str]:
        """Parse a PDF resume into raw text.

        Args:
            file_content: Raw bytes of the PDF file.

        Returns:
            Dictionary with 'raw_text' and 'sections'.
        """
        try:
            import PyPDF2
            import io

            reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

            raw_text = "\n".join(pages_text)
            if not raw_text.strip():
                raise ParsingError("PDF contains no extractable text.")

            cleaned_text = self._clean_text(raw_text)
            sections = self._extract_sections(cleaned_text, RESUME_SECTION_PATTERNS)

            logger.info(f"Parsed resume: {len(cleaned_text)} chars, {len(sections)} sections")
            return {"raw_text": cleaned_text, "sections": sections}

        except ParsingError:
            raise
        except Exception as e:
            logger.error(f"Resume PDF parsing failed: {e}")
            raise ParsingError(f"Failed to parse resume PDF: {str(e)}")

    def parse_resume_text(self, text: str) -> Dict[str, str]:
        """Parse plain text resume.

        Args:
            text: Raw resume text.

        Returns:
            Dictionary with 'raw_text' and 'sections'.
        """
        if not text or not text.strip():
            raise ParsingError("Resume text is empty.")

        cleaned_text = self._clean_text(text)
        sections = self._extract_sections(cleaned_text, RESUME_SECTION_PATTERNS)

        logger.info(f"Parsed resume text: {len(cleaned_text)} chars, {len(sections)} sections")
        return {"raw_text": cleaned_text, "sections": sections}

    def parse_job_description(self, text: str) -> Dict[str, str]:
        """Parse a job description into structured sections.

        Args:
            text: Raw job description text.

        Returns:
            Dictionary with 'raw_text', 'processed_text', and 'sections'.
        """
        if not text or not text.strip():
            raise ParsingError("Job description text is empty.")

        cleaned_text = self._clean_text(text)
        sections = self._extract_sections(cleaned_text, JD_SECTION_PATTERNS)

        logger.info(f"Parsed JD: {len(cleaned_text)} chars, {len(sections)} sections")
        return {
            "raw_text": cleaned_text,
            "processed_text": cleaned_text,
            "sections": sections,
        }

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Remove leading/trailing whitespace per line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)
        # Remove non-printable characters (keep newlines and tabs)
        text = re.sub(r"[^\x20-\x7E\n\t]", "", text)
        # Normalize spaces
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _extract_sections(
        self, text: str, patterns: Dict[str, str]
    ) -> Dict[str, str]:
        """Extract sections from text using regex patterns.

        Returns a dictionary mapping section names to their content.
        """
        sections = {}
        lines = text.split("\n")
        current_section = "header"
        current_content = []

        for line in lines:
            stripped = line.strip()
            # Skip pure separator lines (===, ---, ___)
            if re.match(r"^[-=_*#]{3,}\s*$", stripped):
                continue

            matched_section = None
            for section_name, pattern in patterns.items():
                if re.match(pattern, stripped):
                    matched_section = section_name
                    break

            if matched_section:
                # Save previous section
                if current_content:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = matched_section
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    # Common resume action verbs used to detect plain-text bullets in PDF-parsed text
    _ACTION_VERBS = re.compile(
        r"^(Built|Developed|Designed|Implemented|Led|Created|Managed|Architected|"
        r"Deployed|Optimized|Integrated|Delivered|Collaborated|Improved|Reduced|"
        r"Increased|Automated|Migrated|Refactored|Maintained|Established|Launched|"
        r"Contributed|Spearheaded|Authored|Streamlined|Configured|Engineered)\b",
        re.IGNORECASE,
    )

    # Section heading patterns used to track which section a bullet belongs to
    _SECTION_HEADING = re.compile(
        r"^(experience|work history|employment|projects?|summary|objective|"
        r"education|skills|achievements?|certifications?|activities|volunteer)[:\s]*$",
        re.IGNORECASE,
    )

    def extract_bullet_points(self, text: str, sections: dict | None = None) -> List[Dict]:
        """Extract bullet points with source section context.

        Returns list of dicts: {text, section, section_label}
        """
        bullets: List[Dict] = []

        # If parsed sections are available, process each section separately
        if sections:
            SECTION_DISPLAY = {
                "experience": "Professional Experience",
                "projects": "Projects",
                "summary": "Summary",
                "skills": "Technical Skills",
                "education": "Education",
                "certifications": "Certifications",
                "awards": "Awards & Honors",
                "volunteer": "Volunteer Experience",
                "publications": "Publications",
                "languages": "Languages",
            }
            for section_key, section_text in sections.items():
                display_label = SECTION_DISPLAY.get(section_key, section_key.replace("_", " ").title())
                lines = section_text.split("\n")
                current_sub = None
                heading_started_bullets = False
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # Detect sub-headings: company name, project name, job title
                    # Skip: Tech Stack lines, date-only lines, long lines, bullets,
                    # and lowercase-starting lines (these are PDF-wrapped continuations
                    # of the previous bullet, not new headings)
                    is_tech_stack = bool(re.match(r"(?i)^tech\s*(stack|skills?)\s*:", stripped))
                    is_date_line = bool(re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}", stripped, re.IGNORECASE))
                    is_continuation = bool(re.match(r"^[a-z]", stripped))
                    ends_like_sentence = stripped.endswith(".")
                    heading_candidate = re.sub(r"https?://\S+", "", stripped).strip()
                    if (len(heading_candidate) < 100
                            and heading_candidate
                            and not is_tech_stack
                            and not is_date_line
                            and not is_continuation
                            and not ends_like_sentence
                            and not self._ACTION_VERBS.match(stripped)
                            and not re.match(r"^[\-\*•●○‣–\d]", stripped)
                            and re.search(r"[A-Z]", heading_candidate)):
                        candidate = heading_candidate.split("|")[0].split("·")[0].split(",")[0].strip()
                        if len(candidate) > 80:
                            continue  # too long to be a heading, leave current_sub as-is
                        if current_sub and not heading_started_bullets:
                            # A second heading-like line right after the first (before any
                            # bullets), e.g. a client name under a project title: keep the
                            # first, more descriptive one and ignore this one.
                            continue
                        current_sub = candidate
                        heading_started_bullets = False
                        continue
                    for bullet in self._extract_bullets_from_text(stripped):
                        heading_started_bullets = True
                        label = f"{display_label} - {current_sub}" if current_sub else display_label
                        bullets.append({"text": bullet, "section": section_key, "section_label": label})
            return bullets

        # Fallback: scan raw text, track current heading
        current_section = "experience"
        current_label = "Experience"
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if self._SECTION_HEADING.match(stripped):
                current_section = stripped.lower().rstrip(": ")
                current_label = stripped.rstrip(": ").title()
                continue
            for bullet in self._extract_bullets_from_text(stripped):
                bullets.append({"text": bullet, "section": current_section, "section_label": current_label})
        return bullets

    def _extract_bullets_from_text(self, text: str) -> List[str]:
        """Extract bullet strings from a block of text."""
        results = []
        for line in text.split("\n"):
            line = line.strip()
            if re.match(r"^[\-\*\u2022\u25CF\u25CB\u2023\u2013\u2014]\s+", line):
                bullet = re.sub(r"^[\-\*\u2022\u25CF\u25CB\u2023\u2013\u2014]\s+", "", line).strip()
                if len(bullet) > 10:
                    results.append(bullet)
            elif re.match(r"^\d+[\.\)]\s+", line):
                bullet = re.sub(r"^\d+[\.\)]\s+", "", line).strip()
                if len(bullet) > 10:
                    results.append(bullet)
            elif self._ACTION_VERBS.match(line) and len(line) > 20:
                results.append(line)
        return results
