"""API routes for ATS analysis operations."""

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from src.nlp.skill_normalizer import SkillNormalizer
from src.api.schemas.requests import (
    AnalysisRunRequest,
    FeedbackRequest,
    JobDescriptionUploadRequest,
    ResumeUploadRequest,
)
from src.api.schemas.responses import (
    AnalysisResponse,
    ErrorResponse,
    HistoryItem,
    HistoryResponse,
    JobDescriptionUploadResponse,
    ResumeUploadResponse,
    ScoreBreakdown,
    SkillDetail,
)
from src.api.auth import get_optional_user
from src.cache.cache_manager import get_cache
from src.core.config import get_settings
from src.core.exceptions import AppException
from src.core.logger import get_logger
from src.database.models import (
    ATSAnalysis,
    AnalysisStatus,
    DocumentChunk,
    JobDescription,
    Resume,
    User,
    SkillProgress,
)
from src.database.session import get_db_dependency, SessionLocal
from src.matching.engine import (
    HybridMatchingEngine,
    NEGATED_EVIDENCE_MARKERS,
    SEMANTIC_CONFIDENCE_THRESHOLD,
)
from src.matching.explainer import ExplainabilityEngine
from src.nlp.extractor import SkillExtractor
from src.nlp.parser import DocumentParser
from src.nlp.skill_normalizer import deterministic_normalize
from src.rag.chunker import DocumentChunker
from src.rag.embedder import EmbeddingGenerator
from src.rag.retriever import SemanticRetriever

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

DEBUG_SNIPPET_CHARS = 240

# ─── Dependencies ────────────────────────────────────────────────────────────

parser = DocumentParser()
extractor = SkillExtractor()
chunker = DocumentChunker()
embedder = EmbeddingGenerator()
matcher = HybridMatchingEngine()
explainer = ExplainabilityEngine()
normalizer = SkillNormalizer()
cache = get_cache()


def _debug_trace_enabled() -> bool:
    """Return whether ATS debug tracing should emit structured logs."""
    return bool(settings.ATS_DEBUG_TRACE)


def _select_representative_bullets(bullet_dicts: List[Dict], limit: int = 8) -> List[Dict]:
    """Pick bullets spread across resume sections instead of just the first N.

    A naive [:limit] slice only ever picks from whichever section appears first
    in the resume (usually Experience), so Projects/other sections never get
    optimized. This round-robins across sections to keep coverage even.
    """
    by_section: Dict[str, List[Dict]] = {}
    for b in bullet_dicts:
        by_section.setdefault(b.get("section", "other"), []).append(b)

    selected: List[Dict] = []
    idx = 0
    while len(selected) < limit and any(by_section.values()):
        for section in list(by_section.keys()):
            if idx < len(by_section[section]):
                selected.append(by_section[section][idx])
                if len(selected) >= limit:
                    break
        idx += 1
        if all(idx >= len(v) for v in by_section.values()):
            break
    return selected


def _truncate_debug_text(value: str, limit: int = DEBUG_SNIPPET_CHARS) -> str:
    if not value:
        return ""
    text = " ".join(str(value).split())
    return text[:limit] + ("..." if len(text) > limit else "")


def _skill_debug_view(skills: List[Dict]) -> List[Dict]:
    return [
        {
            "name": skill.get("name"),
            "normalized_name": skill.get("normalized_name"),
            "category": skill.get("category"),
            "confidence": skill.get("confidence"),
            "evidence": _truncate_debug_text(skill.get("evidence", "")),
        }
        for skill in skills
    ]


def _semantic_group_debug_view(group: Dict) -> Dict:
    return {
        "canonical_skill": group.get("canonical_skill"),
        "original_resume_terms": group.get("original_resume_terms", []),
        "original_jd_terms": group.get("original_jd_terms", []),
        "category": group.get("category"),
        "confidence": group.get("confidence"),
        "match_status": group.get("match_status"),
        "evidence_from_resume": _truncate_debug_text(group.get("evidence_from_resume", "")),
        "evidence_from_jd": _truncate_debug_text(group.get("evidence_from_jd", "")),
        "match_reason": _truncate_debug_text(group.get("match_reason", "")),
    }


def _semantic_evidence_traceable(group: Dict, resume_skills: List[Dict]) -> bool:
    evidence = str(group.get("evidence_from_resume", "")).strip()
    if not evidence:
        return False
    evidence_lower = evidence.lower()
    if any(marker in evidence_lower for marker in NEGATED_EVIDENCE_MARKERS):
        return False

    resume_keys = {
        deterministic_normalize(skill.get("name", ""))
        for skill in resume_skills
        if skill.get("name")
    }
    resume_keys |= {
        deterministic_normalize(skill.get("normalized_name", ""))
        for skill in resume_skills
        if skill.get("normalized_name")
    }
    if any(
        deterministic_normalize(term) in resume_keys
        for term in group.get("original_resume_terms", [])
    ):
        return True

    evidence_key = deterministic_normalize(evidence)
    for skill in resume_skills:
        skill_evidence = deterministic_normalize(skill.get("evidence", ""))
        if skill_evidence and (evidence_key in skill_evidence or skill_evidence in evidence_key):
            return True
    return False


def _semantic_rejection_reason(group: Dict, resume_skills: List[Dict]) -> str:
    if float(group.get("confidence", 0.0) or 0.0) < SEMANTIC_CONFIDENCE_THRESHOLD:
        return "confidence_below_threshold"
    if not str(group.get("evidence_from_resume", "")).strip():
        return "missing_evidence_from_resume"
    evidence_lower = str(group.get("evidence_from_resume", "")).lower()
    if any(marker in evidence_lower for marker in NEGATED_EVIDENCE_MARKERS):
        return "negated_placeholder_evidence"
    if not group.get("original_jd_terms"):
        return "missing_original_jd_terms"
    if not group.get("original_resume_terms"):
        return "missing_original_resume_terms"
    if not _semantic_evidence_traceable(group, resume_skills):
        return "untraceable_evidence_from_resume"
    return "accepted"


def _rag_debug_view(semantic_evidence: Dict[str, Dict]) -> Dict[str, Dict]:
    results = {}
    for skill, data in semantic_evidence.items():
        resume_chunks = data.get("resume_evidence", [])
        results[skill] = {
            "has_evidence": data.get("has_evidence", False),
            "max_similarity": data.get("max_similarity", 0.0),
            "resume_evidence": [
                {
                    "similarity": chunk.get("similarity"),
                    "section_type": chunk.get("section_type"),
                    "snippet": _truncate_debug_text(chunk.get("text", "")),
                }
                for chunk in resume_chunks
            ],
        }
    return results


def _rag_diagnostics_debug_view(rag_diagnostics: Optional[Dict[str, Dict]]) -> Dict[str, Dict]:
    results = {}
    for skill, data in (rag_diagnostics or {}).items():
        results[skill] = {
            "resume_id": data.get("resume_id"),
            "chunk_count": data.get("chunk_count"),
            "non_null_embedding_count": data.get("non_null_embedding_count"),
            "rows_exist_after_resume_id_filter": data.get("rows_exist_after_resume_id_filter"),
            "threshold": data.get("threshold"),
            "top_similarities_without_threshold": [
                {
                    **row,
                    "snippet": _truncate_debug_text(row.get("snippet", "")),
                }
                for row in data.get("top_similarities_without_threshold", [])
            ],
        }
    return results


def _match_debug_view(match: Dict) -> Dict:
    return {
        **match,
        "evidence_from_resume": _truncate_debug_text(match.get("evidence_from_resume", "")),
        "evidence_from_jd": _truncate_debug_text(match.get("evidence_from_jd", "")),
        "match_reason": _truncate_debug_text(match.get("match_reason", "")),
    }


def _missing_debug_view(skill: Dict) -> Dict:
    return {
        **skill,
        "missing_reason": _truncate_debug_text(skill.get("missing_reason", "")),
    }


def _missing_failure_stage(
    skill: Dict,
    rejected_groups: List[Dict],
    semantic_evidence: Dict[str, Dict],
    skipped_retrieval: List[str],
) -> str:
    skill_name = skill.get("skill", "")
    for group in rejected_groups:
        if skill_name in group.get("original_jd_terms", []):
            return f"semantic_acceptance:{group.get('rejection_reason')}"
    if skill_name in skipped_retrieval:
        return "rag_not_attempted"
    if skill_name in semantic_evidence:
        evidence = semantic_evidence[skill_name]
        if not evidence.get("has_evidence"):
            return "rag_no_resume_evidence"
    return "matching_no_evidence"


def _emit_ats_debug_trace(
    *,
    analysis_id,
    resume_id,
    jd_id,
    raw_resume_skills: List[Dict],
    raw_jd_skills: List[Dict],
    normalized_resume_skills: List[Dict],
    normalized_jd_skills: List[Dict],
    canonical_groups: List[Dict],
    score_result: Dict,
    semantic_evidence: Dict[str, Dict],
    rag_diagnostics: Optional[Dict[str, Dict]],
    rag_query_terms: List[str],
    skipped_retrieval: List[str],
) -> None:
    if not _debug_trace_enabled():
        return

    accepted_groups = []
    rejected_groups = []
    for group in canonical_groups:
        group_view = _semantic_group_debug_view(group)
        rejection_reason = _semantic_rejection_reason(group, normalized_resume_skills)
        if rejection_reason == "accepted":
            accepted_groups.append(group_view)
        else:
            group_view["rejection_reason"] = rejection_reason
            rejected_groups.append(group_view)

    matched_skills = [_match_debug_view(match) for match in score_result.get("matched_skills", [])]
    missing_skills = [_missing_debug_view(skill) for skill in score_result.get("missing_skills", [])]

    trace = {
        "event": "ats_debug_trace",
        "analysis_id": str(analysis_id),
        "resume_id": str(resume_id),
        "jd_id": str(jd_id),
        "extraction": {
            "raw_resume_skills": _skill_debug_view(raw_resume_skills),
            "raw_jd_skills": _skill_debug_view(raw_jd_skills),
            "normalized_resume_skills": _skill_debug_view(normalized_resume_skills),
            "normalized_jd_skills": _skill_debug_view(normalized_jd_skills),
        },
        "semantic_canonicalization": {
            "accepted_groups": accepted_groups,
            "rejected_groups": rejected_groups,
        },
        "matching": {
            "exact_matches": [m for m in matched_skills if m.get("matched_by") == "exact"],
            "normalized_matches": [
                m
                for m in matched_skills
                if m.get("matched_by") == "normalized"
                and "alias" not in m.get("match_reason", "").lower()
            ],
            "alias_matches": [
                m
                for m in matched_skills
                if m.get("matched_by") == "normalized"
                and "alias" in m.get("match_reason", "").lower()
            ],
            "semantic_matches": [m for m in matched_skills if m.get("matched_by") == "semantic"],
            "rag_matches": [m for m in matched_skills if m.get("matched_by") == "rag"],
            "alternative_group_matches": [
                m for m in matched_skills if m.get("matched_by") == "alternative_group"
            ],
        },
        "rag": {
            "query_terms": rag_query_terms,
            "skipped_from_retrieval": skipped_retrieval,
            "threshold": settings.SIMILARITY_THRESHOLD,
            "results": _rag_debug_view(semantic_evidence),
            "diagnostics": _rag_diagnostics_debug_view(rag_diagnostics),
        },
        "final_decision": {
            "matched_skills": matched_skills,
            "missing_skills": [
                {
                    **skill,
                    "failed_stage": _missing_failure_stage(
                        skill,
                        rejected_groups,
                        semantic_evidence,
                        skipped_retrieval,
                    ),
                }
                for skill in missing_skills
            ],
        },
    }
    logger.info(json.dumps(trace, default=str))


def _matched_skill_keys(score_result: Dict) -> set:
    matched_keys = set()
    for match in score_result.get("matched_skills", []):
        for field in ("skill", "canonical_skill", "resume_skill"):
            value = match.get(field)
            if value:
                matched_keys.add(deterministic_normalize(str(value)))
    return matched_keys


# ─── Resume Endpoints ────────────────────────────────────────────────────────


def _extract_skills_background(resume_id: str, resume_text: str) -> None:
    """Extract skills for a resume after the upload response has already been sent.

    Runs in its own DB session so it does not hold the request's connection
    open for the ~60-90s an OpenAI extraction call can take.
    """
    db = SessionLocal()
    try:
        resume = db.query(Resume).filter(Resume.resume_id == uuid.UUID(resume_id)).first()
        if not resume:
            return
        raw_skills = extractor.extract_skills(resume_text)
        extracted_skills = [
            {"skill": s.get("name", ""), "category": s.get("category", "technical")}
            for s in raw_skills if s.get("name")
        ]
        sections_with_skills = dict(resume.parsed_sections or {})
        sections_with_skills["_skills"] = extracted_skills
        resume.parsed_sections = sections_with_skills
        db.commit()
    except Exception as e:
        logger.warning(f"Background skill extraction failed for resume {resume_id}: {e}")
    finally:
        db.close()


@router.post("/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    request: ResumeUploadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_dependency),
    current_user: User = Depends(get_optional_user),
):
    """Upload and parse a resume.

    Parses the resume text, extracts sections, generates embeddings,
    and stores everything in the database. Skill extraction (an ~60-90s
    OpenAI call) runs in the background after the response is returned,
    so the upload itself completes quickly.
    """
    try:
        # Parse resume
        parsed = parser.parse_resume_text(request.text)

        # Resolve user - prefer authenticated user, fall back to anonymous
        if current_user:
            user = current_user
            user_id = current_user.user_id
        else:
            user_id = request.user_id or uuid.uuid4()
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                user = User(user_id=user_id)
                db.add(user)

        # New upload becomes the active resume
        db.query(Resume).filter(Resume.user_id == user_id).update({"is_active": False})

        # Store resume
        resume = Resume(
            user_id=user_id,
            filename=request.filename,
            raw_text=request.text,
            parsed_text=parsed["raw_text"],
            parsed_sections=parsed["sections"],
            is_active=True,
        )
        db.add(resume)
        db.flush()

        # Chunk and embed
        chunks = chunker.chunk_document(
            parsed["raw_text"], parsed["sections"], "resume"
        )
        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedder.generate_embeddings_batch(chunk_texts)

        for i, chunk_data in enumerate(chunks):
            doc_chunk = DocumentChunk(
                resume_id=resume.resume_id,
                chunk_text=chunk_data["text"],
                chunk_index=chunk_data["index"],
                section_type=chunk_data["section_type"],
                embedding=embeddings[i] if i < len(embeddings) else None,
                metadata=chunk_data["metadata"],
            )
            db.add(doc_chunk)

        db.commit()

        # Skill extraction runs after the response is sent, not blocking the upload
        background_tasks.add_task(
            _extract_skills_background, str(resume.resume_id), request.text
        )

        response_data = {
            "success": True,
            "message": "Resume uploaded and processed successfully",
            "resume_id": resume.resume_id,
            "parsed_sections": list(parsed["sections"].keys()),
            "skill_count": 0,
            "char_count": len(request.text),
        }

        return ResumeUploadResponse(**response_data)

    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Resume upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/upload-file", response_model=ResumeUploadResponse)
async def upload_resume_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db_dependency),
    current_user: User = Depends(get_optional_user),
):
    """Accept a PDF or text file, extract text, then delegate to the normal upload logic."""
    import io
    raw = await file.read()
    filename = file.filename or "resume"

    # Extract text from PDF
    if filename.lower().endswith(".pdf") or file.content_type == "application/pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(raw))
            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF parsing failed: {e}")
    else:
        text = raw.decode("utf-8", errors="replace").strip()

    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Could not extract enough text from the file.")

    from src.api.schemas.requests import ResumeUploadRequest as Req
    req = Req(text=text, filename=filename)
    return await upload_resume(
        request=req,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


# ─── Job Description Endpoints ───────────────────────────────────────────────


@router.post("/job/upload", response_model=JobDescriptionUploadResponse)
async def upload_job_description(
    request: JobDescriptionUploadRequest,
    db: Session = Depends(get_db_dependency),
):
    """Upload and parse a job description."""
    try:
        # Check cache
        cache_key = cache.generate_key(request.text, prefix="jd_parse")
        cached = cache.get(cache_key, "jd_parse")
        if cached:
            return JobDescriptionUploadResponse(**cached)

        # Parse JD
        parsed = parser.parse_job_description(request.text)

        # Derive a title from the text if the caller did not supply one
        title = request.title
        if not title:
            first_line = request.text.strip().split("\n")[0].strip()
            title = first_line[:80] if first_line else "Job Description"

        # Store JD
        jd = JobDescription(
            title=title,
            company=request.company,
            raw_text=request.text,
            processed_text=parsed["processed_text"],
            parsed_requirements=parsed["sections"],
        )
        db.add(jd)
        db.flush()

        # Chunk and embed
        chunks = chunker.chunk_document(
            parsed["raw_text"], parsed["sections"], "job_description"
        )
        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedder.generate_embeddings_batch(chunk_texts)

        for i, chunk_data in enumerate(chunks):
            doc_chunk = DocumentChunk(
                jd_id=jd.jd_id,
                chunk_text=chunk_data["text"],
                chunk_index=chunk_data["index"],
                section_type=chunk_data["section_type"],
                embedding=embeddings[i] if i < len(embeddings) else None,
                metadata=chunk_data["metadata"],
            )
            db.add(doc_chunk)

        db.commit()

        response_data = {
            "success": True,
            "message": "Job description uploaded and processed successfully",
            "jd_id": jd.jd_id,
            "title": title,
            "parsed_sections": list(parsed["sections"].keys()),
            "requirement_count": len(parsed["sections"]),
        }

        cache.set(cache_key, response_data, "jd_parse")

        return JobDescriptionUploadResponse(**response_data)

    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"JD upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Analysis Endpoints ──────────────────────────────────────────────────────


def _run_analysis_background(
    analysis_id: str,
    resume_id: str,
    jd_id: str,
    weights: Optional[Dict],
):
    """Background task: runs full analysis pipeline and writes results to DB."""
    db = SessionLocal()
    start_time = time.time()
    try:
        analysis = db.query(ATSAnalysis).filter(
            ATSAnalysis.analysis_id == analysis_id
        ).first()
        if not analysis:
            return

        resume = db.query(Resume).filter(Resume.resume_id == resume_id).first()
        jd = db.query(JobDescription).filter(JobDescription.jd_id == jd_id).first()
        if not resume or not jd:
            analysis.status = AnalysisStatus.FAILED
            db.commit()
            return

        resume_text = resume.parsed_text or resume.raw_text
        jd_text = jd.processed_text or jd.raw_text

        # Step 1: Parallel skill extraction
        t0 = time.time()
        resume_extract_key = cache.generate_key(resume_text, prefix="resume_skill_extract")
        jd_extract_key = cache.generate_key(jd_text, prefix="jd_skill_extract")

        # Use skills already extracted at upload time (avoids a GPT call)
        stored_skills = (resume.parsed_sections or {}).get("_skills")
        if stored_skills:
            resume_skills = [
                {"name": s["skill"], "category": s.get("category", "technical"), "confidence": 1.0, "evidence": ""}
                for s in stored_skills if s.get("skill")
            ]
            cache.set(resume_extract_key, resume_skills, "skill_extract")
            logger.info(f"[TIMING] Step 1 resume skills loaded from stored data ({len(resume_skills)} skills)")
        else:
            resume_skills = cache.get(resume_extract_key, "skill_extract")

        jd_skills = cache.get(jd_extract_key, "skill_extract")
        if resume_skills is None or jd_skills is None:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {}
                if resume_skills is None:
                    futures["resume"] = pool.submit(extractor.extract_skills, resume_text, "resume")
                if jd_skills is None:
                    futures["jd"] = pool.submit(extractor.extract_skills, jd_text, "job_description")
                if "resume" in futures:
                    resume_skills = futures["resume"].result()
                    cache.set(resume_extract_key, resume_skills, "skill_extract")
                if "jd" in futures:
                    jd_skills = futures["jd"].result()
                    cache.set(jd_extract_key, jd_skills, "skill_extract")
        logger.info(f"[TIMING] Step 1 skill extraction: {int((time.time()-t0)*1000)}ms")

        # Step 2: Normalize skills
        normalization_payload = json.dumps(
            {
                "resume_skills": resume_skills,
                "jd_skills": jd_skills,
                "resume_text": resume_text[:4000],
                "jd_text": jd_text[:4000],
                "version": "semantic-normalization-v6",
            },
            sort_keys=True,
            default=str,
        )
        normalization_key = cache.generate_key(normalization_payload, prefix="skill_semantic_normalization")
        normalized = cache.get(normalization_key, "skill_semantic_normalization")
        if normalized is None:
            t1 = time.time()
            normalized = normalizer.normalize_skill_sets(
                resume_skills=resume_skills,
                jd_skills=jd_skills,
                resume_text=resume_text,
                jd_text=jd_text,
            )
            logger.info(f"[TIMING] Step 2 normalization: {int((time.time()-t1)*1000)}ms")
            cache.set(normalization_key, normalized, "skill_semantic_normalization")

        resume_skills = normalized["resume_skills"]
        jd_skills = normalized["jd_skills"]
        canonical_groups = list(normalized.get("canonical_skill_groups", []))
        alternative_groups = normalized.get("alternative_groups", [])

        # Alias resolution runs outside cache - always fresh, not affected by stale cache
        from src.nlp.skill_normalizer import resolve_ai_tool_aliases
        alias_partials = resolve_ai_tool_aliases(resume_skills, jd_skills)
        for partial in alias_partials:
            key = deterministic_normalize(partial["canonical_skill"])
            idx = next(
                (i for i, g in enumerate(canonical_groups)
                 if deterministic_normalize(g["canonical_skill"]) == key),
                None,
            )
            if idx is None:
                canonical_groups.append(partial)
            elif canonical_groups[idx].get("match_status") == "missing":
                canonical_groups[idx] = partial

        # Step 3: RAG retrieval (batched)
        retriever = SemanticRetriever(db)
        semantic_terms = {
            term
            for group in canonical_groups
            for term in group.get("original_jd_terms", [])
            if group.get("confidence", 0.0) >= 0.8
        }
        if not semantic_terms:
            semantic_terms = {s["name"] for s in jd_skills}
        jd_skill_names = sorted(semantic_terms)
        t2 = time.time()
        semantic_evidence = retriever.retrieve_for_analysis(
            resume_id=resume_id,
            jd_id=jd_id,
            query_skills=jd_skill_names,
        )
        logger.info(f"[TIMING] Step 3 RAG retrieval: {int((time.time()-t2)*1000)}ms")

        # Step 4: Hybrid matching
        if weights:
            engine = HybridMatchingEngine(
                keyword_weight=weights.get("keyword", 0.5),
                semantic_weight=weights.get("semantic", 0.3),
                category_weight=weights.get("category", 0.2),
            )
        else:
            engine = matcher

        score_result = engine.calculate_score(
            resume_skills, jd_skills, semantic_evidence,
            canonical_groups=canonical_groups,
            alternative_groups=alternative_groups,
        )

        matched_keys = _matched_skill_keys(score_result)
        queried_keys = {deterministic_normalize(skill) for skill in jd_skill_names}
        fallback_skill_names = sorted({
            skill["name"] for skill in jd_skills
            if deterministic_normalize(skill["name"]) not in matched_keys
            and deterministic_normalize(skill["name"]) not in queried_keys
        })
        if fallback_skill_names:
            fallback_evidence = retriever.retrieve_for_analysis(
                resume_id=resume_id, jd_id=jd_id, query_skills=fallback_skill_names,
            )
            semantic_evidence.update(fallback_evidence)
            score_result = engine.calculate_score(
                resume_skills, jd_skills, semantic_evidence,
                canonical_groups=canonical_groups, alternative_groups=alternative_groups,
            )

        # Step 5: Explainability
        t3 = time.time()
        explanation = explainer.generate_explanation(score_result, semantic_evidence, resume_text)
        logger.info(f"[TIMING] Step 4 explainability: {int((time.time()-t3)*1000)}ms")

        processing_time = int((time.time() - start_time) * 1000)

        analysis.status = AnalysisStatus.COMPLETED
        analysis.overall_score = score_result["overall_score"]
        analysis.keyword_score = score_result["keyword_score"]
        analysis.semantic_score = score_result["semantic_score"]
        analysis.category_scores = score_result["category_scores"]
        analysis.matched_skills = score_result["matched_skills"]
        analysis.missing_skills = score_result["missing_skills"]
        analysis.recommendations = explanation.get("improvement_priority", [])
        analysis.evidence = explanation.get("evidence", [])
        analysis.explainability_report = explanation
        # Step 6: Bullet optimization - rewrite top resume bullets for this JD
        missing_skill_names = [m["skill"] for m in score_result.get("missing_skills", [])]
        jd_skill_names_all = [s["name"] for s in jd_skills]
        # Re-parse sections with latest patterns (handles resumes uploaded before pattern updates)
        reparsed = parser.parse_resume_text(resume_text)
        resume_sections = reparsed.get("sections") or resume.parsed_sections or {}
        bullet_dicts = parser.extract_bullet_points(resume_text, sections=resume_sections if resume_sections else None)
        selected_bullets = _select_representative_bullets(bullet_dicts, limit=8)
        optimized_bullets = explainer.optimize_bullets(
            bullets=selected_bullets,
            target_skills=jd_skill_names_all,
            missing_skills=missing_skill_names,
        ) if selected_bullets else []

        analysis.optimized_bullets = optimized_bullets
        analysis.processing_time_ms = processing_time

        # Upsert missing skills into skill_progress for this user
        if analysis.user_id:
            for skill_name in missing_skill_names:
                existing = (
                    db.query(SkillProgress)
                    .filter(
                        SkillProgress.user_id == analysis.user_id,
                        SkillProgress.skill_name == skill_name,
                    )
                    .first()
                )
                if not existing:
                    db.add(SkillProgress(
                        user_id=analysis.user_id,
                        skill_name=skill_name,
                        highest_level_passed="none",
                        ready_to_apply="false",
                    ))
                elif existing.is_resolved:
                    # Still missing on this newer analysis: un-resolve it
                    existing.is_resolved = False

            # Auto-resolve: if a previously-tracked gap skill now shows up as
            # matched (the user switched to a resume that has it), mark it
            # resolved instead of deleting - keeps quiz history intact.
            matched_skill_keys = {
                deterministic_normalize(m.get("skill", ""))
                for m in score_result.get("matched_skills", [])
            }
            if matched_skill_keys:
                tracked = (
                    db.query(SkillProgress)
                    .filter(SkillProgress.user_id == analysis.user_id)
                    .all()
                )
                for row in tracked:
                    if deterministic_normalize(row.skill_name) in matched_skill_keys:
                        row.is_resolved = True

        db.commit()
        logger.info(f"[TIMING] Total background analysis: {processing_time}ms")

    except Exception as e:
        logger.error(f"Background analysis failed: {e}")
        try:
            analysis = db.query(ATSAnalysis).filter(ATSAnalysis.analysis_id == analysis_id).first()
            if analysis:
                analysis.status = AnalysisStatus.FAILED
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/analysis/run", response_model=AnalysisResponse)
async def run_analysis(
    request: AnalysisRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_dependency),
    current_user: User = Depends(get_optional_user),
):
    """Submit an ATS analysis job. Returns immediately; poll GET /analysis/{id} for results."""
    resume = db.query(Resume).filter(Resume.resume_id == request.resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    jd = db.query(JobDescription).filter(JobDescription.jd_id == request.jd_id).first()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Prefer authenticated user; fall back to the resume's owner (resume is already auth-gated on upload)
    user_id = (current_user.user_id if current_user else None) or resume.user_id

    analysis = ATSAnalysis(
        resume_id=request.resume_id,
        jd_id=request.jd_id,
        user_id=user_id,
        status=AnalysisStatus.PROCESSING,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    background_tasks.add_task(
        _run_analysis_background,
        str(analysis.analysis_id),
        str(request.resume_id),
        str(request.jd_id),
        request.weights,
    )

    return AnalysisResponse(
        success=True,
        message="Analysis started. Poll GET /analysis/{id} for results.",
        analysis_id=analysis.analysis_id,
        status="processing",
    )


# kept for backward compat - original blocking pipeline (now unused)
async def _run_analysis_blocking(
    request: AnalysisRunRequest,
    db: Session,
):
    """Original blocking pipeline - preserved for reference."""
    start_time = time.time()

    try:
        # Validate inputs exist
        resume = db.query(Resume).filter(Resume.resume_id == request.resume_id).first()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        jd = db.query(JobDescription).filter(JobDescription.jd_id == request.jd_id).first()
        if not jd:
            raise HTTPException(status_code=404, detail="Job description not found")

        # Create analysis record
        analysis = ATSAnalysis(
            resume_id=request.resume_id,
            jd_id=request.jd_id,
            status=AnalysisStatus.PROCESSING,
        )
        db.add(analysis)
        db.flush()

        resume_text = resume.parsed_text or resume.raw_text
        jd_text = jd.processed_text or jd.raw_text

        # Step 1: Extract skills - run resume + JD extraction in parallel
        t0 = time.time()
        resume_extract_key = cache.generate_key(resume_text, prefix="resume_skill_extract")
        jd_extract_key = cache.generate_key(jd_text, prefix="jd_skill_extract")

        # Use skills already extracted at upload time (avoids a GPT call)
        stored_skills = (resume.parsed_sections or {}).get("_skills")
        if stored_skills:
            resume_skills = [
                {"name": s["skill"], "category": s.get("category", "technical"), "confidence": 1.0, "evidence": ""}
                for s in stored_skills if s.get("skill")
            ]
            cache.set(resume_extract_key, resume_skills, "skill_extract")
            logger.info(f"[TIMING] Step 1 resume skills loaded from stored data ({len(resume_skills)} skills)")
        else:
            resume_skills = cache.get(resume_extract_key, "skill_extract")

        jd_skills = cache.get(jd_extract_key, "skill_extract")

        if resume_skills is None or jd_skills is None:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {}
                if resume_skills is None:
                    futures["resume"] = pool.submit(extractor.extract_skills, resume_text, "resume")
                if jd_skills is None:
                    futures["jd"] = pool.submit(extractor.extract_skills, jd_text, "job_description")
                if "resume" in futures:
                    resume_skills = futures["resume"].result()
                    cache.set(resume_extract_key, resume_skills, "skill_extract")
                if "jd" in futures:
                    jd_skills = futures["jd"].result()
                    cache.set(jd_extract_key, jd_skills, "skill_extract")

        logger.info(f"[TIMING] Step 1 skill extraction: {int((time.time()-t0)*1000)}ms")

        raw_resume_skills = resume_skills if _debug_trace_enabled() else []
        raw_jd_skills = jd_skills if _debug_trace_enabled() else []

        normalization_payload = json.dumps(
            {
                "resume_skills": resume_skills,
                "jd_skills": jd_skills,
                "resume_text": resume_text[:4000],
                "jd_text": jd_text[:4000],
                "version": "semantic-normalization-v6",
            },
            sort_keys=True,
            default=str,
        )
        normalization_key = cache.generate_key(
            normalization_payload,
            prefix="skill_semantic_normalization",
        )
        normalized = cache.get(normalization_key, "skill_semantic_normalization")
        if normalized is None:
            t1 = time.time()
            normalized = normalizer.normalize_skill_sets(
                resume_skills=resume_skills,
                jd_skills=jd_skills,
                resume_text=resume_text,
                jd_text=jd_text,
            )
            logger.info(f"[TIMING] Step 2 normalization: {int((time.time()-t1)*1000)}ms")
            cache.set(normalization_key, normalized, "skill_semantic_normalization")

        resume_skills = normalized["resume_skills"]
        jd_skills = normalized["jd_skills"]
        canonical_groups = normalized.get("canonical_skill_groups", [])
        alternative_groups = normalized.get("alternative_groups", [])

        # Step 2: Targeted RAG retrieval
        retriever = SemanticRetriever(db)
        semantic_terms = {
            term
            for group in canonical_groups
            for term in group.get("original_jd_terms", [])
            if group.get("confidence", 0.0) >= 0.8
        }
        if not semantic_terms:
            semantic_terms = {s["name"] for s in jd_skills}
        jd_skill_names = sorted(semantic_terms)
        skipped_retrieval = sorted(
            {s["name"] for s in jd_skills} - set(jd_skill_names)
        ) if _debug_trace_enabled() else []
        rag_diagnostics = {} if _debug_trace_enabled() else None
        t2 = time.time()
        semantic_evidence = retriever.retrieve_for_analysis(
            resume_id=request.resume_id,
            jd_id=request.jd_id,
            query_skills=jd_skill_names,
            diagnostics=rag_diagnostics,
        )
        logger.info(f"[TIMING] Step 3 RAG retrieval: {int((time.time()-t2)*1000)}ms")

        # Step 3: Hybrid matching
        if request.weights:
            engine = HybridMatchingEngine(
                keyword_weight=request.weights.get("keyword", 0.4),
                semantic_weight=request.weights.get("semantic", 0.4),
                category_weight=request.weights.get("category", 0.2),
            )
        else:
            engine = matcher

        score_result = engine.calculate_score(
            resume_skills,
            jd_skills,
            semantic_evidence,
            canonical_groups=canonical_groups,
            alternative_groups=alternative_groups,
        )

        matched_keys = _matched_skill_keys(score_result)
        queried_keys = {deterministic_normalize(skill) for skill in jd_skill_names}
        fallback_skill_names = sorted(
            {
                skill["name"]
                for skill in jd_skills
                if deterministic_normalize(skill["name"]) not in matched_keys
                and deterministic_normalize(skill["name"]) not in queried_keys
            }
        )
        if fallback_skill_names:
            fallback_evidence = retriever.retrieve_for_analysis(
                resume_id=request.resume_id,
                jd_id=request.jd_id,
                query_skills=fallback_skill_names,
                diagnostics=rag_diagnostics,
            )
            semantic_evidence.update(fallback_evidence)
            jd_skill_names = sorted(set(jd_skill_names) | set(fallback_skill_names))
            skipped_retrieval = sorted(
                {s["name"] for s in jd_skills} - set(jd_skill_names)
            ) if _debug_trace_enabled() else []
            score_result = engine.calculate_score(
                resume_skills,
                jd_skills,
                semantic_evidence,
                canonical_groups=canonical_groups,
                alternative_groups=alternative_groups,
            )

        if _debug_trace_enabled():
            _emit_ats_debug_trace(
                analysis_id=analysis.analysis_id,
                resume_id=request.resume_id,
                jd_id=request.jd_id,
                raw_resume_skills=raw_resume_skills,
                raw_jd_skills=raw_jd_skills,
                normalized_resume_skills=resume_skills,
                normalized_jd_skills=jd_skills,
                canonical_groups=canonical_groups,
                score_result=score_result,
                semantic_evidence=semantic_evidence,
                rag_diagnostics=rag_diagnostics,
                rag_query_terms=jd_skill_names,
                skipped_retrieval=skipped_retrieval,
            )

        # Step 4: Explainability
        t3 = time.time()
        explanation = explainer.generate_explanation(
            score_result,
            semantic_evidence,
            resume_text,
)

        logger.info(f"[TIMING] Step 4 explainability: {int((time.time()-t3)*1000)}ms")
        # Step 5: Bullet optimization is intentionally skipped during ATS scoring.
        optimized_bullets = []

        # Calculate processing time
        processing_time = int((time.time() - start_time) * 1000)

        # Update analysis record
        analysis.status = AnalysisStatus.COMPLETED
        analysis.overall_score = score_result["overall_score"]
        analysis.keyword_score = score_result["keyword_score"]
        analysis.semantic_score = score_result["semantic_score"]
        analysis.category_scores = score_result["category_scores"]
        analysis.matched_skills = score_result["matched_skills"]
        analysis.missing_skills = score_result["missing_skills"]
        analysis.recommendations = explanation.get("improvement_priority", [])
        analysis.evidence = explanation.get("evidence", [])
        analysis.explainability_report = explanation
        analysis.optimized_bullets = optimized_bullets
        analysis.processing_time_ms = processing_time
        db.commit()

        return AnalysisResponse(
            success=True,
            message="Analysis completed successfully",
            analysis_id=analysis.analysis_id,
            status="completed",
            score=ScoreBreakdown(
                overall_score=score_result["overall_score"],
                keyword_score=score_result["keyword_score"],
                semantic_score=score_result["semantic_score"],
                category_scores=score_result["category_scores"],
            ),
            matched_skills=[
                SkillDetail(
                    skill=m["skill"],
                    category=m.get("category", "unknown"),
                    match_type=m.get("match_type"),
                    matched_by=m.get("matched_by"),
                    match_reason=m.get("match_reason"),
                    evidence=m.get("evidence_from_resume"),
                    evidence_from_resume=m.get("evidence_from_resume"),
                    confidence=m.get("confidence"),
                )
                for m in score_result["matched_skills"]
            ],
            missing_skills=[
                SkillDetail(
                    skill=m["skill"],
                    category=m.get("category", "unknown"),
                    missing_reason=m.get("missing_reason"),
                )
                for m in score_result["missing_skills"]
            ],
            recommendations=explanation.get("improvement_priority", []),
            explainability=explanation,
            evidence=explanation.get("evidence", []),
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        if 'analysis' in locals():
            analysis.status = AnalysisStatus.FAILED
            db.commit()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db_dependency),
):
    """Retrieve a completed analysis by ID."""
    analysis = db.query(ATSAnalysis).filter(
        ATSAnalysis.analysis_id == analysis_id
    ).first()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    score = None
    if analysis.overall_score is not None:
        score = ScoreBreakdown(
            overall_score=analysis.overall_score,
            keyword_score=analysis.keyword_score or 0,
            semantic_score=analysis.semantic_score or 0,
            category_scores=analysis.category_scores or {},
        )

    return AnalysisResponse(
        success=True,
        message="Analysis retrieved",
        analysis_id=analysis.analysis_id,
        status=analysis.status.value if analysis.status else "unknown",
        score=score,
        matched_skills=[
            SkillDetail(
                skill=m["skill"],
                category=m.get("category", "unknown"),
                match_type=m.get("match_type"),
                matched_by=m.get("matched_by"),
                match_reason=m.get("match_reason"),
                evidence=m.get("evidence_from_resume"),
                evidence_from_resume=m.get("evidence_from_resume"),
                confidence=m.get("confidence"),
            )
            for m in (analysis.matched_skills or [])
        ],
        missing_skills=[
            SkillDetail(
                skill=m["skill"],
                category=m.get("category", "unknown"),
                missing_reason=m.get("missing_reason"),
            )
            for m in (analysis.missing_skills or [])
        ],
        recommendations=analysis.recommendations or [],
        explainability=analysis.explainability_report,
        evidence=analysis.evidence or [],
        optimized_bullets=analysis.optimized_bullets or [],
        processing_time_ms=analysis.processing_time_ms,
    )


# ─── History Endpoint ────────────────────────────────────────────────────────


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db_dependency),
):
    """Retrieve analysis history with pagination."""
    total = db.query(ATSAnalysis).count()
    analyses = (
        db.query(ATSAnalysis)
        .order_by(ATSAnalysis.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []
    for a in analyses:
        # Get related resume and JD info
        resume = db.query(Resume).filter(Resume.resume_id == a.resume_id).first()
        jd = db.query(JobDescription).filter(JobDescription.jd_id == a.jd_id).first()

        items.append(
            HistoryItem(
                analysis_id=a.analysis_id,
                resume_filename=resume.filename if resume else None,
                jd_title=jd.title if jd else None,
                overall_score=a.overall_score,
                status=a.status.value if a.status else "unknown",
                created_at=a.created_at,
            )
        )

    return HistoryResponse(
        success=True,
        message=f"Retrieved {len(items)} analyses",
        total=total,
        items=items,
    )
