"""Hybrid Matching Engine.

Combines deterministic matching, lightweight pattern matching, LLM semantic
canonicalization, RAG evidence, and weighted category scoring.
"""

import re
from typing import Any, Dict, List, Optional, Set

from src.core.config import get_settings
from src.core.logger import get_logger
from src.nlp.skill_normalizer import deterministic_normalize, _is_false_equivalence

logger = get_logger(__name__)
settings = get_settings()

SEMANTIC_CONFIDENCE_THRESHOLD = 0.80
MATCH_COUNTER_KEYS = ("exact", "normalized", "semantic", "rag", "alternative_group")
NEGATED_EVIDENCE_MARKERS = (
    "no direct mention",
    "no evidence",
    "not found",
    "not explicitly mentioned",
)
LIGHTWEIGHT_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
}


class HybridMatchingEngine:
    """Combines layered matching and category-based scoring."""

    def __init__(
        self,
        keyword_weight: float = None,
        semantic_weight: float = None,
        category_weight: float = None,
    ):
        self.keyword_weight = keyword_weight or settings.KEYWORD_WEIGHT
        self.semantic_weight = semantic_weight or settings.SEMANTIC_WEIGHT
        self.category_weight = category_weight or settings.CATEGORY_WEIGHT

    def calculate_score(
        self,
        resume_skills: List[Dict],
        jd_skills: List[Dict],
        semantic_evidence: Dict[str, Dict],
        canonical_groups: Optional[List[Dict[str, Any]]] = None,
        alternative_groups: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict:
        """Calculate the hybrid ATS score using canonical match results."""
        canonical_groups = canonical_groups or []
        alternative_groups = alternative_groups or []

        match_result = self._match_skills(
            resume_skills,
            jd_skills,
            semantic_evidence,
            canonical_groups,
            alternative_groups,
        )
        matched_skills = match_result["matched_skills"]
        missing_skills = match_result["missing_skills"]
        telemetry = match_result["telemetry"]

        keyword_score = self._coverage_score(
            jd_skills,
            matched_skills,
            {"exact", "normalized", "alternative_group"},
        )
        semantic_score = self._coverage_score(
            jd_skills,
            matched_skills,
            {"semantic", "rag"},
        )
        category_result = self._category_score(jd_skills, matched_skills)

        # Unified coverage: all matched skills count, semantic at 85% credit vs exact
        total_jd = len(jd_skills) or 1
        exact_count = sum(
            1 for m in matched_skills
            if m.get("matched_by") in {"exact", "normalized", "alternative_group"}
        )
        semantic_count = sum(
            1 for m in matched_skills
            if m.get("matched_by") in {"semantic", "rag"}
        )
        unified_coverage = (exact_count + 0.85 * semantic_count) / total_jd

        overall_score = (
            0.70 * unified_coverage
            + 0.30 * category_result["score"]
        )

        result = {
            "overall_score": round(overall_score * 100, 1),
            "keyword_score": round(keyword_score * 100, 1),
            "semantic_score": round(semantic_score * 100, 1),
            "category_scores": category_result["breakdown"],
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "match_details": {
                "keyword_matches": [
                    m for m in matched_skills if m["matched_by"] in {"exact", "normalized"}
                ],
                "semantic_matches": [
                    m for m in matched_skills if m["matched_by"] == "semantic"
                ],
                "rag_matches": [m for m in matched_skills if m["matched_by"] == "rag"],
                "alternative_group_matches": [
                    m for m in matched_skills if m["matched_by"] == "alternative_group"
                ],
                "synonym_matches": [],
            },
            "telemetry": telemetry,
            "weights_used": {
                "keyword": self.keyword_weight,
                "semantic": self.semantic_weight,
                "category": self.category_weight,
            },
        }

        logger.info(
            f"Hybrid score: {result['overall_score']}% "
            f"(keyword={result['keyword_score']}%, semantic={result['semantic_score']}%)"
        )
        return result

    def _match_skills(
        self,
        resume_skills: List[Dict],
        jd_skills: List[Dict],
        semantic_evidence: Dict[str, Dict],
        canonical_groups: List[Dict[str, Any]],
        alternative_groups: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        resume_index = self._build_resume_index(resume_skills)
        matched: Dict[str, Dict[str, Any]] = {}
        satisfied_keys: Set[str] = set()
        telemetry = {key: 0 for key in MATCH_COUNTER_KEYS}

        for group in alternative_groups:
            match = self._match_alternative_group(group, resume_index)
            if not match:
                continue
            key = deterministic_normalize(match["skill"])
            matched[key] = match
            telemetry["alternative_group"] += 1
            for option in group.get("options", []):
                satisfied_keys.add(deterministic_normalize(option))

        for jd_skill in jd_skills:
            jd_name = jd_skill["name"]
            jd_key = deterministic_normalize(jd_name)
            if jd_key in satisfied_keys or jd_key in matched:
                continue

            exact = self._find_exact_match(jd_name, resume_skills)
            if exact:
                matched[jd_key] = self._make_match(
                    skill=jd_name,
                    resume_skill=exact,
                    matched_by="exact",
                    match_reason="Exact skill name match.",
                    evidence_from_resume=self._evidence_for_skill(exact),
                    confidence=1.0,
                    category=jd_skill.get("category", "unknown"),
                )
                telemetry["exact"] += 1
                continue

            normalized = resume_index.get(jd_key)
            if normalized:
                matched[jd_key] = self._make_match(
                    skill=jd_name,
                    resume_skill=normalized,
                    matched_by="normalized",
                    match_reason="Matched after deterministic formatting normalization.",
                    evidence_from_resume=self._evidence_for_skill(normalized),
                    confidence=1.0,
                    category=jd_skill.get("category", "unknown"),
                )
                telemetry["normalized"] += 1
                continue

            lightweight = self._find_lightweight_match(jd_key, resume_index)
            if lightweight:
                matched[jd_key] = self._make_match(
                    skill=jd_name,
                    resume_skill=lightweight,
                    matched_by="normalized",
                    match_reason="Matched by existing lightweight alias handling.",
                    evidence_from_resume=self._evidence_for_skill(lightweight),
                    confidence=0.95,
                    category=jd_skill.get("category", "unknown"),
                )
                telemetry["normalized"] += 1
                continue

            phrase = self._phrase_match(jd_key, set(resume_index.keys()))
            if phrase:
                resume_skill = resume_index[phrase]
                matched[jd_key] = self._make_match(
                    skill=jd_name,
                    resume_skill=resume_skill,
                    matched_by="normalized",
                    match_reason="Matched by existing lightweight phrase handling.",
                    evidence_from_resume=self._evidence_for_skill(resume_skill),
                    confidence=0.9,
                    category=jd_skill.get("category", "unknown"),
                )
                telemetry["normalized"] += 1

        for group in canonical_groups:
            if not self._semantic_group_accepted(group, resume_skills):
                continue
            for jd_term in group.get("original_jd_terms", []):
                jd_key = deterministic_normalize(jd_term)
                if jd_key in matched or jd_key in satisfied_keys:
                    continue
                matched[jd_key] = self._make_match(
                    skill=jd_term,
                    resume_skill=", ".join(group.get("original_resume_terms", [])),
                    matched_by="semantic",
                    match_reason=group.get("match_reason", "LLM semantic canonicalization linked the skills."),
                    evidence_from_resume=group.get("evidence_from_resume", ""),
                    confidence=float(group.get("confidence", 0.0)),
                    category=group.get("category", "unknown"),
                    canonical_skill=group.get("canonical_skill"),
                    evidence_from_jd=group.get("evidence_from_jd", ""),
                )
                telemetry["semantic"] += 1

        for jd_skill in jd_skills:
            jd_name = jd_skill["name"]
            jd_key = deterministic_normalize(jd_name)
            if jd_key in matched or jd_key in satisfied_keys:
                continue
            evidence = semantic_evidence.get(jd_name, {})
            if evidence.get("has_evidence"):
                snippet = self._snippet_from_evidence(evidence)
                if not snippet:
                    continue
                matched[jd_key] = self._make_match(
                    skill=jd_name,
                    resume_skill=None,
                    matched_by="rag",
                    match_reason="RAG retrieval found supporting resume evidence above threshold.",
                    evidence_from_resume=snippet,
                    confidence=float(evidence.get("max_similarity", 0.0)),
                    category=jd_skill.get("category", "unknown"),
                )
                telemetry["rag"] += 1

        missing = self._get_missing_skills(jd_skills, list(matched.values()), satisfied_keys)
        return {
            "matched_skills": list(matched.values()),
            "missing_skills": missing,
            "telemetry": telemetry,
        }

    def _semantic_group_accepted(
        self,
        group: Dict[str, Any],
        resume_skills: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        return (
            float(group.get("confidence", 0.0)) >= SEMANTIC_CONFIDENCE_THRESHOLD
            and self._semantic_evidence_traceable(group, resume_skills or [])
            and bool(group.get("original_jd_terms"))
            and bool(group.get("original_resume_terms"))
        )

    def _semantic_evidence_traceable(
        self,
        group: Dict[str, Any],
        resume_skills: List[Dict[str, Any]],
    ) -> bool:
        evidence = str(group.get("evidence_from_resume", "")).strip()
        if not evidence:
            return False
        evidence_lower = evidence.lower()
        if any(marker in evidence_lower for marker in NEGATED_EVIDENCE_MARKERS):
            return False

        resume_index = self._build_resume_index(resume_skills)
        for term in group.get("original_resume_terms", []):
            if deterministic_normalize(term) in resume_index:
                return True

        evidence_key = deterministic_normalize(evidence)
        for skill in resume_skills:
            skill_evidence = deterministic_normalize(skill.get("evidence", ""))
            if skill_evidence and (evidence_key in skill_evidence or skill_evidence in evidence_key):
                return True
        return False

    def _match_alternative_group(
        self, group: Dict[str, Any], resume_index: Dict[str, Dict]
    ) -> Optional[Dict[str, Any]]:
        for option in group.get("options", []):
            resume_skill = resume_index.get(deterministic_normalize(option))
            if not resume_skill:
                continue
            return self._make_match(
                skill=group.get("canonical_skill") or " OR ".join(group.get("options", [])),
                resume_skill=resume_skill,
                matched_by="alternative_group",
                match_reason=f"Alternative requirement satisfied by {resume_skill.get('name', option)}.",
                evidence_from_resume=self._evidence_for_skill(resume_skill),
                confidence=1.0,
                category=group.get("category", "unknown"),
                canonical_skill=group.get("canonical_skill"),
                evidence_from_jd=group.get("evidence_from_jd", ""),
            )
        return None

    def _make_match(
        self,
        skill: str,
        resume_skill: Optional[Dict[str, Any]],
        matched_by: str,
        match_reason: str,
        evidence_from_resume: str,
        confidence: float,
        category: str = "unknown",
        canonical_skill: Optional[str] = None,
        evidence_from_jd: str = "",
    ) -> Dict[str, Any]:
        resume_skill_name = resume_skill.get("name") if isinstance(resume_skill, dict) else resume_skill
        return {
            "skill": skill,
            "canonical_skill": canonical_skill or skill,
            "resume_skill": resume_skill_name,
            "matched_by": matched_by,
            "match_type": matched_by,
            "match_reason": match_reason,
            "evidence_from_resume": evidence_from_resume,
            "evidence_from_jd": evidence_from_jd,
            "confidence": round(confidence, 4),
            "category": category,
            "has_evidence": bool(evidence_from_resume),
        }

    def _get_missing_skills(
        self,
        jd_skills: List[Dict],
        matched_skills: List[Dict],
        satisfied_keys: Optional[Set[str]] = None,
    ) -> List[Dict]:
        satisfied_keys = satisfied_keys or set()
        matched_names = self._matched_skill_keys(matched_skills)

        missing = []
        for skill in jd_skills:
            skill_key = deterministic_normalize(skill["name"])
            if skill_key in matched_names or skill_key in satisfied_keys:
                continue
            missing.append(
                {
                    "skill": skill["name"],
                    "missing_reason": "No exact, normalized, semantic, RAG, or alternative-group evidence found.",
                    "category": skill.get("category", "unknown"),
                    "importance": "high" if skill.get("category") == "core" else "medium",
                }
            )
        return missing

    def _category_score(self, jd_skills: List[Dict], matched_skills: List[Dict]) -> Dict:
        category_weights = {
            "core": 2.0,
            "technical": 1.5,
            "functional": 1.2,
            "behavioral": 0.8,
            "supporting": 0.6,
        }
        matched_names = self._matched_skill_keys(matched_skills)

        category_scores: Dict[str, Dict[str, float]] = {}
        for skill in jd_skills:
            category = skill.get("category", "supporting")
            category_scores.setdefault(
                category,
                {"total": 0, "matched": 0, "weight": category_weights.get(category, 1.0)},
            )
            category_scores[category]["total"] += 1
            if deterministic_normalize(skill["name"]) in matched_names:
                category_scores[category]["matched"] += 1

        total_weighted = 0.0
        max_weighted = 0.0
        breakdown = {}
        for category, data in category_scores.items():
            weight = data["weight"]
            cat_score = data["matched"] / data["total"] if data["total"] else 0.0
            total_weighted += cat_score * weight * data["total"]
            max_weighted += weight * data["total"]
            breakdown[category] = {
                "score": round(cat_score * 100, 1),
                "matched": data["matched"],
                "total": data["total"],
                "weight": weight,
            }

        return {
            "score": min(total_weighted / max_weighted if max_weighted else 0.0, 1.0),
            "breakdown": breakdown,
        }

    def _matched_skill_keys(self, matched_skills: List[Dict]) -> Set[str]:
        fields = ("skill", "canonical_skill", "resume_skill")
        matched_names: Set[str] = set()
        for match in matched_skills:
            for field in fields:
                value = match.get(field)
                if value:
                    matched_names.add(deterministic_normalize(str(value)))
        return matched_names

    def _coverage_score(
        self, jd_skills: List[Dict], matched_skills: List[Dict], match_types: Set[str]
    ) -> float:
        total_jd = len(jd_skills) if jd_skills else 1
        covered = {
            deterministic_normalize(m["skill"])
            for m in matched_skills
            if m.get("matched_by") in match_types
        }
        return min(len(covered) / total_jd, 1.0)

    def _keyword_match(self, resume_skills: List[Dict], jd_skills: List[Dict]) -> Dict:
        """Backward-compatible unit-test helper for deterministic matching."""
        result = self._match_skills(resume_skills, jd_skills, {}, [], [])
        matches = [
            {
                "jd_skill": m["skill"],
                "resume_skill": m.get("resume_skill"),
                "match_type": m.get("matched_by"),
            }
            for m in result["matched_skills"]
            if m.get("matched_by") in {"exact", "normalized"}
        ]
        synonym_matches = [
            match
            for match in matches
            if "lightweight alias" in (
                next(
                    (
                        m.get("match_reason", "")
                        for m in result["matched_skills"]
                        if m["skill"] == match["jd_skill"]
                    ),
                    "",
                )
            )
        ]
        return {
            "score": len(matches) / (len(jd_skills) if jd_skills else 1),
            "matches": matches,
            "synonym_matches": synonym_matches,
            "unmatched": [m["skill"] for m in result["missing_skills"]],
            "total_required": len(jd_skills) if jd_skills else 1,
            "total_matched": len(matches),
        }

    def _semantic_match(self, jd_skills: List[Dict], semantic_evidence: Dict[str, Dict]) -> Dict:
        matches = []
        total_similarity = 0.0
        for skill in jd_skills:
            skill_name = skill["name"]
            evidence = semantic_evidence.get(skill_name, {})
            if evidence.get("has_evidence", False):
                similarity = float(evidence.get("max_similarity", 0.0))
                total_similarity += similarity
                matches.append(
                    {
                        "skill": skill_name,
                        "similarity": similarity,
                        "evidence_count": len(evidence.get("resume_evidence", [])),
                    }
                )

        total_jd = len(jd_skills) if jd_skills else 1
        coverage = len(matches) / total_jd
        avg_similarity = total_similarity / len(matches) if matches else 0.0
        score = (coverage * 0.6) + (avg_similarity * 0.4)
        return {
            "score": min(score, 1.0),
            "matches": matches,
            "coverage": coverage,
            "avg_similarity": round(avg_similarity, 4),
        }

    def _build_resume_index(self, resume_skills: List[Dict]) -> Dict[str, Dict]:
        index = {}
        for skill in resume_skills:
            index[deterministic_normalize(skill.get("name", ""))] = skill
            if skill.get("normalized_name"):
                index[deterministic_normalize(skill["normalized_name"])] = skill
        return index

    def _find_exact_match(self, jd_name: str, resume_skills: List[Dict]) -> Optional[Dict]:
        jd_exact = jd_name.lower().strip()
        for skill in resume_skills:
            if skill.get("name", "").lower().strip() == jd_exact:
                return skill
        return None

    def _find_lightweight_match(
        self, jd_key: str, resume_index: Dict[str, Dict]
    ) -> Optional[Dict]:
        alias = LIGHTWEIGHT_ALIASES.get(jd_key)
        if alias and alias in resume_index:
            return resume_index[alias]
        for short, expanded in LIGHTWEIGHT_ALIASES.items():
            if jd_key == expanded and short in resume_index:
                return resume_index[short]
        return None

    def _evidence_for_skill(self, skill: Optional[Dict[str, Any]]) -> str:
        if not isinstance(skill, dict):
            return ""
        return str(skill.get("evidence") or skill.get("name") or "").strip()

    def _snippet_from_evidence(self, evidence: Dict[str, Any]) -> str:
        chunks = evidence.get("resume_evidence", [])
        if not chunks:
            return ""
        return str(chunks[0].get("text", "")).strip()

    def _phrase_match(self, skill: str, resume_skills: Set[str]) -> Optional[str]:
        for resume_skill in resume_skills:
            if _is_false_equivalence(skill, resume_skill):
                continue
            if skill in resume_skill or resume_skill in skill:
                if len(skill) > 3 and len(resume_skill) > 3:
                    return resume_skill
        return None
