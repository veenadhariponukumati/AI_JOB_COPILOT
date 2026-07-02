"""Skill normalization for canonical resume/JD skill matching."""

import json
import re
from typing import Any, Dict, List

from openai import OpenAI

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


# Pairs of technologies that are commonly confused due to similar names but are
# NOT equivalent. If the LLM groups any of these together, we reject the group
# rather than accept the false equivalence.
FALSE_EQUIVALENCE_PAIRS: List[tuple] = [
    ("java", "javascript"),
    ("c", "c#"),
    ("c", "c++"),
    ("c#", "c++"),
    ("react", "reactnative"),
    ("node", "nodered"),
    ("objectivec", "objectivec++"),
]


def _is_false_equivalence(term_a: str, term_b: str) -> bool:
    a, b = deterministic_normalize(term_a), deterministic_normalize(term_b)
    if a == b:
        return False
    for x, y in FALSE_EQUIVALENCE_PAIRS:
        if {a, b} == {x, y}:
            return True
    return False


# AI tool alias map: if a resume mentions the company, it implies the product.
# Used to generate partial matches with a recommendation to be explicit.
AI_TOOL_ALIASES: Dict[str, Dict] = {
    "anthropic": {
        "implies": "Claude",
        "confidence": 0.82,
        "tip": "Consider mentioning 'Claude' explicitly instead of just 'Anthropic'.",
    },
    "openai": {
        "implies": "ChatGPT",
        "confidence": 0.82,
        "tip": "Consider mentioning 'ChatGPT' or 'GPT-4' explicitly instead of just 'OpenAI'.",
    },
    "google deepmind": {
        "implies": "Gemini",
        "confidence": 0.82,
        "tip": "Consider mentioning 'Gemini' explicitly instead of just 'Google DeepMind'.",
    },
    "google": {
        "implies": "Gemini",
        "confidence": 0.81,
        "tip": "If you used Gemini, mention it explicitly rather than just 'Google'.",
    },
    "meta": {
        "implies": "Llama",
        "confidence": 0.81,
        "tip": "If you used Llama/Meta AI, mention it explicitly.",
    },
    "microsoft": {
        "implies": "Copilot",
        "confidence": 0.81,
        "tip": "Consider mentioning 'GitHub Copilot' explicitly if that's what you used.",
    },
    "github": {
        "implies": "Copilot",
        "confidence": 0.82,
        "tip": "Consider mentioning 'GitHub Copilot' explicitly.",
    },
}


def deterministic_normalize(value: str) -> str:
    """Normalize formatting-only differences for deterministic matching."""
    if not value:
        return ""
    # Strip trailing version numbers (e.g. "Next.js 16" → "Next.js", "React 19" → "React")
    value = re.sub(r"\s+v?\d+(\.\d+)*$", "", value.strip(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", value.lower().strip())


def resolve_ai_tool_aliases(
    resume_skills: List[Dict[str, Any]],
    jd_skills: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Check if resume mentions an AI company when the JD asks for its product.
    Returns partial match groups with tips to be more explicit.
    """
    partial_matches = []
    jd_skill_names_normalized = {deterministic_normalize(s.get("name", "")) for s in jd_skills}
    resume_terms_normalized = {deterministic_normalize(s.get("name", "")): s for s in resume_skills}

    for company_term, alias_info in AI_TOOL_ALIASES.items():
        company_key = deterministic_normalize(company_term)
        implied_tool = alias_info["implies"]
        implied_key = deterministic_normalize(implied_tool)

        # Match resume skills that start with or contain the company name
        # e.g. "anthropic api" should match alias key "anthropic"
        matching_resume_term = next(
            (term for term in resume_terms_normalized if term.startswith(company_key) or company_key in term),
            None,
        )

        # JD asks for the tool (e.g. Claude) but resume only mentions company (e.g. Anthropic)
        if implied_key in jd_skill_names_normalized and matching_resume_term:
            resume_skill_obj = resume_terms_normalized.get(matching_resume_term)
            resume_display = resume_skill_obj.get("name", company_term.title()) if resume_skill_obj else company_term.title()
            partial_matches.append({
                "canonical_skill": implied_tool,
                "original_resume_terms": [resume_display],
                "original_jd_terms": [implied_tool],
                "category": "technical",
                "confidence": alias_info["confidence"],
                "match_status": "partial",
                "evidence_from_resume": f"Resume mentions '{resume_display}' which implies {implied_tool}.",
                "evidence_from_jd": f"JD requires '{implied_tool}'.",
                "match_reason": f"'{resume_display}' is the company/platform behind {implied_tool}. Partial match - {alias_info['tip']}",
            })

    return partial_matches


class SkillNormalizer:
    """Normalizes extracted resume and JD skills into canonical skill groups."""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE if settings.OPENAI_API_BASE else None,
        )
        self.model = settings.OPENAI_MODEL

    def normalize_skill_sets(
        self,
        resume_skills: List[Dict[str, Any]],
        jd_skills: List[Dict[str, Any]],
        resume_text: str,
        jd_text: str,
    ) -> Dict[str, Any]:
        """Normalize semantically equivalent skills before matching."""
        prompt = self._build_prompt(resume_skills, jd_skills, resume_text, jd_text)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You normalize ATS skills into canonical JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content.strip()
            result = json.loads(content)
            return self._coerce_result(result, resume_skills, jd_skills, jd_text)

        except Exception as e:
            logger.error(f"Skill normalization failed: {e}")
            return self._fallback_result(resume_skills, jd_skills, jd_text)

    def _build_prompt(
        self,
        resume_skills: List[Dict[str, Any]],
        jd_skills: List[Dict[str, Any]],
        resume_text: str,
        jd_text: str,
    ) -> str:
        return f"""
You are a semantic skill canonicalization engine for an ATS resume matching system.

Use semantic reasoning only for conceptual equivalence. Deterministic formatting
matches are handled elsewhere.

Rules:
- Do not invent skills unsupported by the resume or job description.
- Do not mark a semantic match unless resume evidence exists.
- Preserve original resume and JD terms.
- Use confidence 0.0-1.0.
- Mark missing only when no resume term/evidence supports the JD term.
- NEVER group similarly-named but distinct technologies as equivalent, e.g.
  "Java" and "JavaScript" are different languages, "C" and "C#" and "C++" are
  different languages, "React" and "React Native" are different, "Node" and
  "Node-RED" are different. Sharing a text prefix is not evidence of equivalence.
- Return ONLY valid JSON.

Resume skills:
{json.dumps(resume_skills, default=str)}

Job description skills:
{json.dumps(jd_skills, default=str)}

Resume text excerpt:
{resume_text[:4000]}

Job description text excerpt:
{jd_text[:4000]}

Return JSON in this exact format:
{{
  "canonical_skill_groups": [
    {{
      "canonical_skill": "canonical skill name",
      "original_resume_terms": ["terms from resume"],
      "original_jd_terms": ["terms from JD"],
      "category": "technical|functional|behavioral|core|supporting",
      "confidence": 0.0,
      "match_status": "exact|semantic|partial|missing",
      "evidence_from_resume": "short exact resume evidence",
      "evidence_from_jd": "short JD evidence",
      "match_reason": "brief reason"
    }}
  ]
}}
"""

    def _coerce_result(
        self,
        result: Dict[str, Any],
        resume_skills: List[Dict[str, Any]],
        jd_skills: List[Dict[str, Any]],
        jd_text: str,
    ) -> Dict[str, Any]:
        groups = result.get("canonical_skill_groups", [])
        if not isinstance(groups, list):
            groups = []

        coerced_groups = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            resume_terms = self._as_string_list(group.get("original_resume_terms"))
            jd_terms = self._as_string_list(group.get("original_jd_terms"))

            # Reject groups that pair up known false-equivalence terms
            # (e.g. LLM incorrectly matching "Java" resume experience to a "JavaScript" JD requirement)
            if any(_is_false_equivalence(r, j) for r in resume_terms for j in jd_terms):
                logger.warning(
                    f"Rejected false-equivalence skill group: resume={resume_terms} jd={jd_terms}"
                )
                continue

            coerced_groups.append(
                {
                    "canonical_skill": str(group.get("canonical_skill", "")).strip(),
                    "original_resume_terms": resume_terms,
                    "original_jd_terms": jd_terms,
                    "category": group.get("category", "unknown"),
                    "confidence": float(group.get("confidence", 0.0) or 0.0),
                    "match_status": group.get("match_status", "semantic"),
                    "evidence_from_resume": str(group.get("evidence_from_resume", "")).strip(),
                    "evidence_from_jd": str(group.get("evidence_from_jd", "")).strip(),
                    "match_reason": str(group.get("match_reason", "")).strip(),
                }
            )

        alias_partials = resolve_ai_tool_aliases(resume_skills, jd_skills)
        # Merge alias partials - replace GPT's "missing" group with alias partial
        # (GPT marks Claude as missing because resume says "Anthropic", not "Claude";
        # but our alias logic knows Anthropic implies Claude as a partial match)
        for partial in alias_partials:
            key = deterministic_normalize(partial["canonical_skill"])
            idx = next(
                (i for i, g in enumerate(coerced_groups)
                 if deterministic_normalize(g["canonical_skill"]) == key),
                None,
            )
            if idx is None:
                coerced_groups.append(partial)
            elif coerced_groups[idx].get("match_status") == "missing":
                # GPT said missing, but we have alias evidence → upgrade to partial
                coerced_groups[idx] = partial

        return {
            "resume_skills": self._with_deterministic_names(resume_skills),
            "jd_skills": self._with_deterministic_names(jd_skills),
            "canonical_skill_groups": coerced_groups,
            "alternative_groups": self.detect_alternative_groups(jd_text, jd_skills),
        }

    def _fallback_result(
        self,
        resume_skills: List[Dict[str, Any]],
        jd_skills: List[Dict[str, Any]],
        jd_text: str,
    ) -> Dict[str, Any]:
        alias_partials = resolve_ai_tool_aliases(resume_skills, jd_skills)
        return {
            "resume_skills": self._with_deterministic_names(resume_skills),
            "jd_skills": self._with_deterministic_names(jd_skills),
            "canonical_skill_groups": alias_partials,
            "alternative_groups": self.detect_alternative_groups(jd_text, jd_skills),
        }

    def _with_deterministic_names(self, skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for skill in skills:
            item = dict(skill)
            item["normalized_name"] = deterministic_normalize(item.get("name", ""))
            normalized.append(item)
        return normalized

    def detect_alternative_groups(
        self, jd_text: str, jd_skills: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect explicit OR-style alternative requirement groups."""
        groups = []
        skill_names = [skill.get("name", "") for skill in jd_skills]
        skill_keys = {deterministic_normalize(name): name for name in skill_names}

        patterns = [
            r"(?P<prefix>one\s+additional\s+[^.:\n]*?(?:such\s+as|including)?)\s*:?\s*(?P<options>[A-Za-z0-9+#./_\-\s,]+?\s+or\s+(?:similar|[A-Za-z0-9+#./_\-]+))",
            r"(?P<options>[A-Za-z0-9+#./_\-]+(?:\s*,\s*[A-Za-z0-9+#./_\-]+)*\s+or\s+[A-Za-z0-9+#./_\-]+)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, jd_text, flags=re.IGNORECASE):
                options = self._extract_options(match.group("options"))
                concrete_options = [
                    option for option in options if deterministic_normalize(option) != "similar"
                ]
                if len(concrete_options) < 2:
                    continue
                matched_options = [
                    skill_keys[deterministic_normalize(option)]
                    for option in concrete_options
                    if deterministic_normalize(option) in skill_keys
                ]
                if len(matched_options) < 2:
                    continue
                group_name = " OR ".join(matched_options)
                groups.append(
                    {
                        "canonical_skill": group_name,
                        "options": matched_options,
                        "category": self._category_for_options(jd_skills, matched_options),
                        "evidence_from_jd": match.group(0).strip(),
                    }
                )

        deduped = {}
        for group in groups:
            key = "|".join(sorted(deterministic_normalize(o) for o in group["options"]))
            deduped[key] = group
        return list(deduped.values())

    def _extract_options(self, value: str) -> List[str]:
        value = re.sub(r"\bor\s+similar\b", ", similar", value, flags=re.IGNORECASE)
        value = re.sub(r"\bor\b", ",", value, flags=re.IGNORECASE)
        return [part.strip(" .;:\n\t") for part in value.split(",") if part.strip()]

    def _category_for_options(self, jd_skills: List[Dict[str, Any]], options: List[str]) -> str:
        option_keys = {deterministic_normalize(option) for option in options}
        for skill in jd_skills:
            if deterministic_normalize(skill.get("name", "")) in option_keys:
                return skill.get("category", "unknown")
        return "unknown"

    def _as_string_list(self, value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []
