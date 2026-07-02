"""Skill extraction and classification pipeline.

Uses OpenAI API for intelligent skill extraction with validation rules
to prevent generic words from being classified as skills.
"""

import json
import re
from typing import Dict, List

from openai import OpenAI

from src.core.config import get_settings
from src.core.exceptions import ExtractionError
from src.core.logger import get_logger
from src.nlp.skill_normalizer import deterministic_normalize

logger = get_logger(__name__)
settings = get_settings()

# ─── Validation Rules ────────────────────────────────────────────────────────

# Words that should NEVER be classified as skills
GENERIC_WORD_BLOCKLIST = {
    "team",
    "work",
    "good",
    "great",
    "excellent",
    "strong",
    "ability",
    "responsible",
    "responsible for",
    "experience",
    "knowledge",
    "understanding",
    "familiar",
    "proficient",
    "skilled",
    "capable",
    "competent",
    "detail",
    "detail-oriented",
    "self-motivated",
    "motivated",
    "passionate",
    "dedicated",
    "hard-working",
    "fast learner",
    "quick learner",
    "results-driven",
    "dynamic",
    "innovative",
    "creative",
    "proactive",
    "flexible",
    "adaptable",
    "reliable",
    "dependable",
    "organized",
    "analytical",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "been",
    "will",
    "can",
    "are",
    "was",
    "were",
    "has",
    "had",
    "not",
    "but",
    "all",
    "any",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "than",
    "too",
    "very",
    "just",
    "also",
}

# Minimum length for a skill name
MIN_SKILL_LENGTH = 2
MAX_SKILL_LENGTH = 60


EXTRACTION_PROMPT = """You are a technical recruiter AI that extracts skills from documents.

Given the following text, extract all concrete, specific skills mentioned.

RULES:
1. Only extract SPECIFIC, NAMED technologies, tools, methodologies, or domain skills.
2. DO NOT extract generic adjectives or soft personality traits (e.g., "hard-working", "detail-oriented").
3. DO NOT extract common English words or phrases that are not actual skills.
4. Each skill must be something that can be tested or validated.
5. Normalize skill names (e.g., "JS" -> "JavaScript", "ML" -> "Machine Learning").
6. Preserve compound AI application skills as dedicated concepts when present,
   including LLM Application Patterns, RAG, Orchestration, Function Calling,
   and AI Assistant Integration. Do not collapse these into generic Machine Learning.
7. Classify each skill into exactly ONE category:
   - technical: Programming languages, frameworks, tools, platforms, databases
   - functional: Domain knowledge, business processes, methodologies (e.g., Agile, Scrum)
   - behavioral: Measurable soft skills (e.g., public speaking, technical writing, mentoring)
   - core: Skills that are central requirements for the role
   - supporting: Nice-to-have or supplementary skills

Return a JSON array of objects with this schema:
{
  "skills": [
    {
      "name": "Skill Name (properly capitalized)",
      "category": "technical|functional|behavioral|core|supporting",
      "confidence": 0.0-1.0,
      "evidence": "exact quote from text where this skill was mentioned"
    }
  ]
}

TEXT:
"""

CLASSIFICATION_PROMPT = """Given a list of skills extracted from a job description and a resume, classify each skill as:
- "core": Essential/required for the role
- "supporting": Nice-to-have or supplementary

Consider the job description context to determine which skills are core vs supporting.

Job Description Context:
{jd_context}

Skills to classify:
{skills_list}

Return JSON:
{{
  "classifications": [
    {{"skill": "name", "category": "core|supporting", "reason": "brief explanation"}}
  ]
}}
"""


class SkillExtractor:
    """Extracts and classifies skills from documents using OpenAI API."""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE if settings.OPENAI_API_BASE else None,
        )
        self.model = settings.OPENAI_MODEL

    def extract_skills(self, text: str, document_type: str = "resume") -> List[Dict]:
        """Extract skills from text using LLM with validation.

        Args:
            text: Document text to extract skills from.
            document_type: Either 'resume' or 'job_description'.

        Returns:
            List of skill dictionaries with name, category, confidence, evidence.
        """
        if not text or len(text.strip()) < 20:
            logger.warning("Text too short for skill extraction")
            return []

        try:
            # Truncate only extremely long texts (most resumes are well under this)
            max_chars = 16000
            input_text = text[:max_chars] if len(text) > max_chars else text

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise skill extraction system. Return only valid JSON.",
                    },
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT + input_text,
                    },
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            raw_skills = result.get("skills", [])

            # Apply validation pipeline
            validated_skills = self._validate_skills(raw_skills)

            logger.info(
                f"Extracted {len(validated_skills)} skills from {document_type} "
                f"(filtered {len(raw_skills) - len(validated_skills)} invalid)"
            )
            return validated_skills

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            raise ExtractionError("LLM returned invalid JSON for skill extraction")
        except Exception as e:
            logger.error(f"Skill extraction failed: {e}")
            raise ExtractionError(f"Skill extraction failed: {str(e)}")

    def classify_skills_for_role(self, skills: List[str], jd_text: str) -> List[Dict]:
        """Classify extracted skills as core or supporting for a specific role.

        Args:
            skills: List of skill names.
            jd_text: Job description text for context.

        Returns:
            List of classification results.
        """
        if not skills:
            return []

        try:
            prompt = CLASSIFICATION_PROMPT.format(
                jd_context=jd_text[:4000],
                skills_list=json.dumps(skills),
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a skill classification system. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            return result.get("classifications", [])

        except Exception as e:
            logger.error(f"Skill classification failed: {e}")
            # Return default classifications
            return [{"skill": s, "category": "supporting", "reason": "classification failed"} for s in skills]

    def normalize_skill_name(self, skill_name: str) -> str:
        """Normalize a skill name for consistent matching.

        Examples:
            'javascript' -> 'javascript'
            'React.js' -> 'reactjs'
            'Machine Learning' -> 'machine learning'
        """
        return deterministic_normalize(skill_name)

    def _validate_skills(self, raw_skills: List[Dict]) -> List[Dict]:
        """Apply validation rules to filter out invalid skills.

        Validation pipeline:
        1. Check against blocklist
        2. Check minimum/maximum length
        3. Check confidence threshold
        4. Remove duplicates (by normalized name)
        """
        validated = []
        seen_normalized = set()

        for skill in raw_skills:
            name = skill.get("name", "").strip()
            confidence = skill.get("confidence", 0.0)

            # Rule 1: Blocklist check
            if name.lower() in GENERIC_WORD_BLOCKLIST:
                logger.debug(f"Blocked generic word: {name}")
                continue

            # Rule 2: Length check
            if len(name) < MIN_SKILL_LENGTH or len(name) > MAX_SKILL_LENGTH:
                logger.debug(f"Skill name length invalid: {name}")
                continue

            # Rule 3: Confidence threshold
            if confidence < settings.SKILL_CONFIDENCE_THRESHOLD:
                logger.debug(f"Low confidence skill filtered: {name} ({confidence})")
                continue

            # Rule 4: Deduplication
            normalized = self.normalize_skill_name(name)
            if normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)

            # Rule 5: Must contain at least one letter
            if not re.search(r"[a-zA-Z]", name):
                continue

            validated.append(
                {
                    "name": name,
                    "normalized_name": normalized,
                    "category": skill.get("category", "technical"),
                    "confidence": confidence,
                    "evidence": skill.get("evidence", ""),
                }
            )

        # Limit total skills
        return validated[: settings.MAX_SKILLS_PER_DOCUMENT]
