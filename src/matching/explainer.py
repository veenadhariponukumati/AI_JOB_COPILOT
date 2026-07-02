"""Explainability Layer.

Generates human-readable explanations for every ATS score,
detailing why points were awarded or deducted.

Every score output includes:
- Why points were awarded
- Why points were deducted
- Which requirements matched
- Which requirements were missing
- Supporting evidence from the resume
"""
import re
import json
from typing import Dict, List, Optional

from openai import OpenAI

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

EXPLANATION_PROMPT = """You are an ATS scoring explainability system.

Given the following scoring data, generate a clear, structured explanation of the ATS score.

SCORING DATA:
- Overall Score: {overall_score}%
- Keyword Score: {keyword_score}%
- Semantic Score: {semantic_score}%
- Matched Skills: {matched_count}
- Missing Skills: {missing_count}
- Total Required: {total_required}

MATCHED SKILLS:
{matched_skills_text}

MISSING SKILLS:
{missing_skills_text}

CATEGORY BREAKDOWN:
{category_breakdown}

Generate a JSON response with this structure:
{{
  "summary": "2-3 sentence overall assessment",
  "points_awarded": [
    {{"reason": "why points were given", "skills": ["skill1"], "points": 10}}
  ],
  "points_deducted": [
    {{"reason": "why points were lost", "skills": ["skill1"], "points": -5}}
  ],
  "requirements_matched": [
    {{"requirement": "requirement text", "evidence": "how it was matched"}}
  ],
  "requirements_missing": [
    {{"requirement": "requirement text", "impact": "high/medium/low", "suggestion": "how to address this gap - for AI tools like Cursor, Copilot, Claude, suggest building a small project with the tool and adding it to GitHub/resume"}}
  ],
  "improvement_priority": ["ordered list of most impactful improvements - for missing AI tools, suggest a specific learning action like 'Build a project using Cursor to demonstrate hands-on experience'"]
}}
"""

BULLET_OPTIMIZATION_PROMPT = """You are a resume optimization expert. Your job is to help candidates present their EXISTING experience more effectively, NOT to add skills they don't have.

Rules:
1. Only incorporate terms from the job requirements if they describe something ALREADY present in the original bullet.
2. Use strong action verbs (replace weak verbs like "worked on", "helped with", "was responsible for").
3. NEVER invent percentages, numbers, or metrics not in the original bullet.
4. If the original has no numbers, do NOT add any quantified claims.
5. NEVER add a technology, tool, or skill that is not mentioned or clearly implied by the original bullet. Do not add "Next.js", "AI coding tools", or any other skill just because it appears in the job requirements.
6. If no improvement is possible without fabricating content, return the original bullet unchanged and leave changes_made and keywords_added empty.

Original bullet: {original_bullet}

Job requirements (for context only, do not add terms that are not already reflected in the bullet): {target_skills}

Return JSON:
{{
  "original": "original bullet text",
  "optimized": "rewritten bullet with stronger verbs, same facts, no new skills added",
  "changes_made": ["short description of each real wording change, empty list if unchanged"],
  "keywords_added": ["job-relevant terms from the job requirements list that matched something already in the bullet and were emphasized, empty list if none"],
  "score_impact": "low/medium/high"
}}
"""


class ExplainabilityEngine:
    """Generates detailed explanations for ATS scores."""

    def _normalize_text(self, value: str) -> str:
        if not value:
            return ""

        value = value.lower().strip()

        # remove punctuation, spaces, separators
        value = re.sub(r"[^a-z0-9]+", "", value)

        return value
    
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE if settings.OPENAI_API_BASE else None,
        )
        self.model = settings.OPENAI_MODEL

    def generate_explanation(
        self,
        score_result: Dict,
        semantic_evidence: Dict[str, Dict],
        resume_text: str = "",
    ) -> Dict:
        """Generate a complete explainability report for an ATS score.

        Args:
            score_result: Output from HybridMatchingEngine.calculate_score()
            semantic_evidence: RAG retrieval evidence map.

        Returns:
            Structured explanation with points awarded/deducted and evidence.
        """
        try:
            # Format matched skills text
            matched_text = "\n".join(
                (
                    f"- {m['skill']} (matched via "
                    f"{m.get('matched_by', m.get('match_type', 'unknown'))}; "
                    f"reason: {m.get('match_reason', 'N/A')})"
                )
                for m in score_result.get("matched_skills", [])
            )

            # Format missing skills text
            missing_text = "\n".join(
                f"- {m['skill']} ({m.get('category', 'unknown')}, importance: {m.get('importance', 'medium')})"
                for m in score_result.get("missing_skills", [])
            )

            # Format category breakdown
            category_text = "\n".join(
                f"- {cat}: {data['score']}% ({data['matched']}/{data['total']} matched, weight: {data['weight']})"
                for cat, data in score_result.get("category_scores", {}).items()
            )

            prompt = EXPLANATION_PROMPT.format(
                overall_score=score_result.get("overall_score", 0),
                keyword_score=score_result.get("keyword_score", 0),
                semantic_score=score_result.get("semantic_score", 0),
                matched_count=len(score_result.get("matched_skills", [])),
                missing_count=len(score_result.get("missing_skills", [])),
                total_required=len(score_result.get("matched_skills", [])) + len(score_result.get("missing_skills", [])),
                matched_skills_text=matched_text or "None",
                missing_skills_text=missing_text or "None",
                category_breakdown=category_text or "N/A",
            )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an ATS scoring explainability system. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )

            explanation = json.loads(response.choices[0].message.content)

            # Enrich with evidence from RAG
            explanation["evidence"] = self._compile_evidence(
                semantic_evidence,
                score_result.get("matched_skills", []),
                resume_text,
)

            logger.info("Generated explainability report")
            return explanation

        except Exception as e:
            logger.error(f"Explanation generation failed: {e}")
            return self._fallback_explanation(score_result)

    def optimize_bullets(
        self,
        bullets: List,
        target_skills: List[str],
        missing_skills: List[str] = None,
    ) -> List[Dict]:
        """Optimize resume bullet points for ATS compatibility.

        Accepts List[str] or List[Dict] with {text, section, section_label}.
        """
        optimized = []

        for bullet_item in bullets[:10]:
            if isinstance(bullet_item, dict):
                bullet = bullet_item.get("text", "")
                section_label = bullet_item.get("section_label", "")
                section = bullet_item.get("section", "")
            else:
                bullet = str(bullet_item)
                section_label = ""
                section = ""

            if not bullet:
                continue

            try:
                prompt = BULLET_OPTIMIZATION_PROMPT.format(
                    original_bullet=bullet,
                    target_skills=", ".join(target_skills[:15]),
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a resume optimization expert. Return only valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )

                result = json.loads(response.choices[0].message.content)
                result["section"] = section
                result["section_label"] = section_label
                optimized.append(result)

            except Exception as e:
                logger.warning(f"Bullet optimization failed: {e}")
                optimized.append({
                    "original": bullet,
                    "optimized": bullet,
                    "section": section,
                    "section_label": section_label,
                    "changes_made": [],
                    "keywords_added": [],
                    "score_impact": "unknown",
                })

        return optimized

    def _compile_evidence(
        self,
        semantic_evidence: Dict[str, Dict],
        matched_skills: List[Dict],
        resume_text: str = "",
    ) -> List[Dict]:
        """Compile evidence for both semantic and keyword matches."""

        evidence_by_skill = {}
        resume_search = self._normalize_text(resume_text)

        for match in matched_skills:
            skill = match.get("skill", "")
            resume_skill = match.get("resume_skill", "")
            key = skill.lower().strip()

            direct_evidence = str(match.get("evidence_from_resume", "")).strip()
            matched_by = match.get("matched_by", match.get("match_type", ""))
            if direct_evidence:
                # For semantic matches, verify evidence actually mentions the JD skill.
                # Normalization GPT sometimes uses the resume_skill text (e.g. React)
                # as evidence for a different JD skill (e.g. Next.js) - wrong snippet.
                skill_in_evidence = bool(re.search(re.escape(skill), direct_evidence, re.IGNORECASE))
                if matched_by == "semantic" and not skill_in_evidence and resume_text:
                    # Search original resume text for the actual skill name
                    m = re.search(re.escape(skill), resume_text, re.IGNORECASE)
                    if m:
                        start = max(m.start() - 120, 0)
                        end = min(m.end() + 220, len(resume_text))
                        direct_evidence = resume_text[start:end].strip()
                evidence_by_skill[key] = {
                    "skill": skill,
                    "found_in_resume": True,
                    "similarity": match.get("confidence", match.get("similarity", 1.0)),
                    "evidence_snippets": [direct_evidence],
                    "matched_by": matched_by,
                    "match_reason": match.get("match_reason", ""),
                }
                continue

            semantic = semantic_evidence.get(skill, {})
            if semantic.get("has_evidence"):
                snippets = [
                    chunk["text"][:300]
                    for chunk in semantic.get("resume_evidence", [])[:2]
                    if chunk.get("text")
                ]
                if snippets:
                    evidence_by_skill[key] = {
                        "skill": skill,
                        "found_in_resume": True,
                        "similarity": semantic.get("max_similarity", 0.0),
                        "evidence_snippets": snippets,
                        "matched_by": match.get("matched_by", match.get("match_type")),
                        "match_reason": match.get("match_reason", ""),
                    }
                    continue

            # Search JD skill name first in ORIGINAL text using regex
            # (normalized index ≠ original text index - causes wrong snippets)
            search_terms = [
                skill,
                skill.replace("-", " "),
                skill.replace("_", " "),
                resume_skill,
            ]

            found_snippet = None

            for term in search_terms:
                if not term or len(term) < 2:
                    continue
                pattern = re.escape(term)
                m = re.search(pattern, resume_text, re.IGNORECASE)
                if m:
                    start = max(m.start() - 120, 0)
                    end = min(m.end() + 220, len(resume_text))
                    found_snippet = resume_text[start:end].strip()
                    break

            if found_snippet:
                evidence_by_skill[key] = {
                    "skill": skill,
                    "found_in_resume": True,
                    "similarity": match.get("confidence", match.get("similarity", 1.0)),
                    "evidence_snippets": [found_snippet],
                    "matched_by": match.get("matched_by", match.get("match_type")),
                    "match_reason": match.get("match_reason", ""),
                }

        return list(evidence_by_skill.values())

    def _fallback_explanation(self, score_result: Dict) -> Dict:
        """Generate a basic explanation without LLM (fallback)."""
        matched = score_result.get("matched_skills", [])
        missing = score_result.get("missing_skills", [])

        return {
            "summary": (
                f"Your resume matched {len(matched)} out of "
                f"{len(matched) + len(missing)} required skills, "
                f"achieving an overall score of {score_result.get('overall_score', 0)}%."
            ),
            "points_awarded": [
                {"reason": f"Matched skill: {m['skill']}", "skills": [m["skill"]], "points": 5}
                for m in matched[:5]
            ],
            "points_deducted": [
                {"reason": f"Missing skill: {m['skill']}", "skills": [m["skill"]], "points": -5}
                for m in missing[:5]
            ],
            "requirements_matched": [
                {"requirement": m["skill"], "evidence": f"Matched via {m.get('match_type', 'analysis')}"}
                for m in matched
            ],
            "requirements_missing": [
                {"requirement": m["skill"], "impact": m.get("importance", "medium"), "suggestion": "Add to resume"}
                for m in missing
            ],
            "improvement_priority": [m["skill"] for m in missing[:5]],
            "evidence": [],
        }
