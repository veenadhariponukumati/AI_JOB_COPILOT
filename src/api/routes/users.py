"""User profile and resume management routes."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from src.api.auth import get_current_user, get_optional_user, fetch_clerk_profile
from src.core.config import get_settings
from src.core.email import send_email
from src.core.rate_limit import limiter
from src.database.session import get_db_dependency as get_db
from src.database.models import User, Resume, ATSAnalysis, SkillProgress, UserFeedback
from src.nlp.extractor import SkillExtractor

settings = get_settings()

router = APIRouter(prefix="/users", tags=["users"])
feedback_router = APIRouter(tags=["feedback"])


# ── Response schemas ──────────────────────────────────────────────────────────

class UserProfileResponse(BaseModel):
    user_id: UUID
    clerk_id: str
    email: str | None
    full_name: str | None

    class Config:
        from_attributes = True


class ResumeResponse(BaseModel):
    resume_id: UUID
    filename: str | None
    upload_timestamp: str
    char_count: int
    is_active: bool

    class Config:
        from_attributes = True


class ResumeRenameRequest(BaseModel):
    filename: str


class SkillProgressResponse(BaseModel):
    skill_name: str
    highest_level_passed: str
    ready_to_apply: str
    is_resolved: bool
    easy_passed_at: str | None
    medium_passed_at: str | None
    hard_passed_at: str | None

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfileResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/me/resumes", response_model=List[ResumeResponse])
def list_resumes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resumes = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.user_id)
        .order_by(Resume.upload_timestamp.desc())
        .all()
    )
    return [
        ResumeResponse(
            resume_id=r.resume_id,
            filename=r.filename,
            upload_timestamp=r.upload_timestamp.isoformat(),
            char_count=len(r.raw_text or ""),
            is_active=r.is_active,
        )
        for r in resumes
    ]


@router.delete("/me/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = db.query(Resume).filter(
        Resume.resume_id == resume_id,
        Resume.user_id == current_user.user_id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    was_active = resume.is_active
    db.delete(resume)
    db.flush()
    if was_active:
        # Promote the most recently uploaded remaining resume to active
        next_resume = (
            db.query(Resume)
            .filter(Resume.user_id == current_user.user_id)
            .order_by(Resume.upload_timestamp.desc())
            .first()
        )
        if next_resume:
            next_resume.is_active = True
    db.commit()


@router.post("/me/resumes/{resume_id}/activate", response_model=ResumeResponse)
def set_active_resume(
    resume_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = db.query(Resume).filter(
        Resume.resume_id == resume_id,
        Resume.user_id == current_user.user_id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    db.query(Resume).filter(Resume.user_id == current_user.user_id).update({"is_active": False})
    resume.is_active = True
    db.commit()
    db.refresh(resume)
    return ResumeResponse(
        resume_id=resume.resume_id,
        filename=resume.filename,
        upload_timestamp=resume.upload_timestamp.isoformat(),
        char_count=len(resume.raw_text or ""),
        is_active=resume.is_active,
    )


@router.patch("/me/resumes/{resume_id}", response_model=ResumeResponse)
def rename_resume(
    resume_id: UUID,
    request: ResumeRenameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = db.query(Resume).filter(
        Resume.resume_id == resume_id,
        Resume.user_id == current_user.user_id,
    ).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")
    new_name = request.filename.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="Filename cannot be empty.")
    resume.filename = new_name
    db.commit()
    db.refresh(resume)
    return ResumeResponse(
        resume_id=resume.resume_id,
        filename=resume.filename,
        upload_timestamp=resume.upload_timestamp.isoformat(),
        char_count=len(resume.raw_text or ""),
        is_active=resume.is_active,
    )


@router.get("/me/skills", response_model=List[SkillProgressResponse])
def get_skill_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SkillProgress)
        .filter(SkillProgress.user_id == current_user.user_id)
        .order_by(SkillProgress.skill_name)
        .all()
    )
    return [
        SkillProgressResponse(
            skill_name=r.skill_name,
            highest_level_passed=r.highest_level_passed,
            ready_to_apply=r.ready_to_apply,
            is_resolved=r.is_resolved,
            easy_passed_at=r.easy_passed_at.isoformat() if r.easy_passed_at else None,
            medium_passed_at=r.medium_passed_at.isoformat() if r.medium_passed_at else None,
            hard_passed_at=r.hard_passed_at.isoformat() if r.hard_passed_at else None,
        )
        for r in rows
    ]


@router.delete("/me/skills", status_code=status.HTTP_204_NO_CONTENT)
def clear_skill_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Wipe all tracked gap skills and quiz progress for a fresh start."""
    db.query(SkillProgress).filter(SkillProgress.user_id == current_user.user_id).delete()
    db.commit()


@router.delete("/me/skills/{skill_name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_skill_progress(
    skill_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a single tracked skill (e.g. a resolved one the user wants to dismiss)."""
    db.query(SkillProgress).filter(
        SkillProgress.user_id == current_user.user_id,
        SkillProgress.skill_name == skill_name,
    ).delete()
    db.commit()


@router.get("/me/resume-skills")
def get_resume_skills(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Extract skills from the user's active resume."""
    resume = (
        db.query(Resume)
        .filter(Resume.user_id == current_user.user_id, Resume.is_active == True)  # noqa: E712
        .first()
    ) or (
        db.query(Resume)
        .filter(Resume.user_id == current_user.user_id)
        .order_by(Resume.upload_timestamp.desc())
        .first()
    )
    if not resume:
        return {"skills": [], "resume_filename": None, "error": None, "pending": False}

    # Use cached skills from upload if available (fast path, no OpenAI call)
    stored = (resume.parsed_sections or {}).get("_skills")
    if stored:
        return {"skills": stored, "resume_filename": resume.filename, "error": None, "pending": False}

    # A background extraction is kicked off right after upload and can take
    # up to ~90s. If the resume was uploaded very recently, don't race it
    # with a duplicate live extraction here - just tell the frontend to
    # keep polling instead of erroring.
    from datetime import datetime, timedelta
    if resume.upload_timestamp and datetime.utcnow() - resume.upload_timestamp < timedelta(seconds=100):
        return {"skills": [], "resume_filename": resume.filename, "error": None, "pending": True}

    # Fallback: extract now (background task likely finished or never ran -
    # e.g. resume uploaded before this feature existed). Retry a couple
    # times to absorb transient OpenAI/DB blips.
    if not resume.raw_text:
        return {"skills": [], "resume_filename": resume.filename, "error": None, "pending": False}
    import time as _time
    last_error = None
    for attempt in range(3):
        try:
            extractor = SkillExtractor()
            raw = extractor.extract_skills(resume.raw_text)
            skills = [{"skill": s.get("name", ""), "category": s.get("category", "technical")} for s in raw if s.get("name")]
            try:
                sections = dict(resume.parsed_sections or {})
                sections["_skills"] = skills
                resume.parsed_sections = sections
                db.commit()
            except Exception:
                db.rollback()
            return {"skills": skills, "resume_filename": resume.filename, "error": None, "pending": False}
        except Exception as e:
            last_error = e
            if attempt < 2:
                _time.sleep(1.5)
    try:
        raise last_error
    except Exception as e:
        return {"skills": [], "resume_filename": resume.filename, "error": str(e), "pending": False}


@router.get("/me/history")
def get_analysis_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    analyses = (
        db.query(ATSAnalysis)
        .filter(ATSAnalysis.user_id == current_user.user_id)
        .order_by(ATSAnalysis.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "analysis_id": str(a.analysis_id),
            "status": a.status.value if hasattr(a.status, "value") else a.status,
            "overall_score": a.overall_score,
            "jd_title": a.job_description.title if a.job_description else None,
            "resume_filename": a.resume.filename if a.resume else None,
            "created_at": a.created_at.isoformat(),
        }
        for a in analyses
    ]


# ── Feedback ──────────────────────────────────────────────────────────────────

class UserFeedbackRequest(BaseModel):
    category: str = Field("general", description="bug, suggestion, or general")
    message: str = Field(..., min_length=1, max_length=5000)


class UserFeedbackResponse(BaseModel):
    feedback_id: UUID
    category: str
    message: str
    created_at: str

    class Config:
        from_attributes = True


@feedback_router.post("/feedback", response_model=UserFeedbackResponse)
@limiter.limit("5/minute")
def submit_feedback(
    request: Request,
    body: UserFeedbackRequest,
    background_tasks: BackgroundTasks,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    entry = UserFeedback(
        user_id=current_user.user_id if current_user else None,
        category=body.category,
        message=body.message.strip(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    submitter_email = "Unknown"
    submitter_name = ""
    if current_user:
        profile = fetch_clerk_profile(current_user.clerk_id)
        submitter_email = profile["email"] or "Unknown"
        submitter_name = profile["name"] or ""
    else:
        submitter_email = "Anonymous (not signed in)"

    from_line = f"{submitter_name} ({submitter_email})" if submitter_name else submitter_email
    html = f"""
    <p><strong>Category:</strong> {entry.category}</p>
    <p><strong>From:</strong> {from_line}</p>
    <p><strong>Message:</strong></p>
    <p>{entry.message}</p>
    <p style="color:#888;font-size:12px;">Submitted {entry.created_at.isoformat()}</p>
    """
    background_tasks.add_task(
        send_email,
        settings.FEEDBACK_NOTIFY_EMAIL,
        f"[AI Job Copilot] New {entry.category} feedback",
        html,
    )

    return UserFeedbackResponse(
        feedback_id=entry.feedback_id,
        category=entry.category,
        message=entry.message,
        created_at=entry.created_at.isoformat(),
    )


@feedback_router.get("/users/me/feedback", response_model=List[UserFeedbackResponse])
def list_my_feedback(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = (
        db.query(UserFeedback)
        .filter(UserFeedback.user_id == current_user.user_id)
        .order_by(UserFeedback.created_at.desc())
        .all()
    )
    return [
        UserFeedbackResponse(
            feedback_id=e.feedback_id,
            category=e.category,
            message=e.message,
            created_at=e.created_at.isoformat(),
        )
        for e in entries
    ]
