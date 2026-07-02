"""API routes for skill validation quizzes."""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from openai import OpenAI

from src.api.schemas.requests import QuizStartRequest, QuizSubmitRequest
from src.api.schemas.responses import (
    QuizQuestion,
    QuizResultResponse,
    QuizStartResponse,
)
from src.core.config import get_settings
from src.core.logger import get_logger
from src.database.models import ATSAnalysis, QuizResult, SkillProgress
from src.database.session import get_db_dependency

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

# Skills whose plain name is ambiguous with an unrelated technical term.
# Without this hint, an LLM defaults to the more common technical meaning
# (e.g. "Cursor" -> SQL database cursor, not the Cursor AI code editor).
SKILL_DISAMBIGUATION = {
    "cursor": "Cursor, the AI-powered code editor (not a SQL/database cursor)",
    "copilot": "GitHub Copilot, the AI coding assistant (not a general autopilot/copilot concept)",
    "claude": "Claude, Anthropic's AI assistant",
    "chatgpt": "ChatGPT, OpenAI's AI assistant",
    "gemini": "Gemini, Google's AI assistant",
}

QUIZ_GENERATION_PROMPT = """Generate {num_questions} multiple-choice questions to validate practical, hands-on knowledge of: {skill_context}

Difficulty level: {difficulty}
- easy: fundamental concepts and basic usage any beginner should know
- medium: applied scenarios requiring hands-on experience and understanding of trade-offs
- hard: advanced, nuanced usage, edge cases, and expert-level judgment calls

The {difficulty} questions must be clearly harder or more advanced than what an easier
difficulty level would ask, and must use different scenarios/wording than a lower difficulty
would use for the same skill. Do not reuse the same question stems across difficulty levels.

Each question should:
1. Test practical, applied knowledge (not trivia)
2. Have exactly 4 options (A, B, C, D)
3. Have exactly one correct answer
4. Be relevant to a professional context

CRITICAL - answer key accuracy: For each question, before writing the final "correct_answer",
independently work out the real answer step by step as if you were answering the question
yourself (e.g. actually trace through any code, actually recall the real API/language behavior).
Only after deriving the true answer should you pick which option letter matches it. Double-check
that the option text at that letter genuinely matches your derived answer word-for-word in meaning.
If you are not fully confident in a question's correctness, discard it and write a different,
more clear-cut question instead. Getting the answer key wrong is a critical failure.

Return JSON:
{{
  "questions": [
    {{
      "question": "question text",
      "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
      "correct_answer": "A",
      "explanation": "why this is correct, referencing the actual reasoning/trace"
    }}
  ]
}}
"""


@router.post("/quiz/start", response_model=QuizStartResponse)
async def start_quiz(
    request: QuizStartRequest,
    db: Session = Depends(get_db_dependency),
):
    """Start a skill validation quiz.

    Generates questions using OpenAI based on the skill and difficulty.
    """
    try:
        # Validate analysis exists
        analysis = db.query(ATSAnalysis).filter(
            ATSAnalysis.analysis_id == request.analysis_id
        ).first()
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")

        # Generate questions
        client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE if settings.OPENAI_API_BASE else None,
        )

        skill_context = SKILL_DISAMBIGUATION.get(
            request.skill.strip().lower(), request.skill
        )
        prompt = QUIZ_GENERATION_PROMPT.format(
            num_questions=request.num_questions,
            skill_context=skill_context,
            difficulty=request.difficulty,
        )

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a technical quiz generator. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        questions_data = result.get("questions", [])

        # Create quiz record
        quiz = QuizResult(
            analysis_id=request.analysis_id,
            user_id=analysis.user_id,
            skill_tested=request.skill,
            difficulty=request.difficulty,
            questions=questions_data,
        )
        db.add(quiz)
        db.commit()

        # Format response
        questions = [
            QuizQuestion(
                question_id=i + 1,
                question=q["question"],
                options=q["options"],
                difficulty=request.difficulty,
            )
            for i, q in enumerate(questions_data)
        ]

        return QuizStartResponse(
            success=True,
            message="Quiz generated successfully",
            quiz_id=quiz.quiz_id,
            skill=request.skill,
            questions=questions,
            total_questions=len(questions),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")


@router.post("/quiz/submit", response_model=QuizResultResponse)
async def submit_quiz(
    request: QuizSubmitRequest,
    db: Session = Depends(get_db_dependency),
):
    """Submit quiz answers and get results."""
    try:
        quiz = db.query(QuizResult).filter(
            QuizResult.quiz_id == request.quiz_id
        ).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        # Grade answers
        questions = quiz.questions or []
        correct_count = 0
        details = []

        for i, answer in enumerate(request.answers):
            if i >= len(questions):
                break

            question = questions[i]
            user_answer = answer.get("answer", "").strip().upper()
            correct_answer = question.get("correct_answer", "").strip().upper()
            is_correct = user_answer == correct_answer

            if is_correct:
                correct_count += 1

            details.append({
                "question_id": i + 1,
                "user_answer": user_answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "explanation": question.get("explanation", ""),
            })

        total = len(questions)
        score = (correct_count / total * 100) if total > 0 else 0
        passed = "pass" if score >= 70 else "partial" if score >= 50 else "fail"

        # Update quiz record
        quiz.answers = request.answers
        quiz.score = score
        quiz.passed = passed
        from datetime import datetime
        now = datetime.utcnow()
        quiz.completed_at = now
        db.commit()

        # Persist pass results to skill_progress so the UI badges reflect real progress
        if passed == "pass" and quiz.user_id:
            level_order = {"easy": 1, "medium": 2, "hard": 3}
            level = (quiz.difficulty or "easy").lower()
            progress = (
                db.query(SkillProgress)
                .filter(
                    SkillProgress.user_id == quiz.user_id,
                    SkillProgress.skill_name == quiz.skill_tested,
                )
                .first()
            )
            if not progress:
                progress = SkillProgress(
                    user_id=quiz.user_id,
                    skill_name=quiz.skill_tested,
                    highest_level_passed="none",
                    ready_to_apply="false",
                )
                db.add(progress)

            if level == "easy":
                progress.easy_passed_at = now
            elif level == "medium":
                progress.medium_passed_at = now
            elif level == "hard":
                progress.hard_passed_at = now

            current_rank = level_order.get(progress.highest_level_passed, 0)
            if level_order.get(level, 0) > current_rank:
                progress.highest_level_passed = level
            if progress.highest_level_passed == "hard":
                progress.ready_to_apply = "true"

            db.commit()

        return QuizResultResponse(
            success=True,
            message=f"Quiz completed. Score: {score:.0f}%",
            quiz_id=quiz.quiz_id,
            score=score,
            passed=passed,
            correct_answers=correct_count,
            total_questions=total,
            details=details,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quiz submission failed: {e}")
        raise HTTPException(status_code=500, detail=f"Quiz submission failed: {str(e)}")
