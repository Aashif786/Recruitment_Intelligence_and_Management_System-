from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, BackgroundTasks, Body
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload, load_only
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, timedelta
import json
import os
import random
import logging
import asyncio
import traceback
import tempfile
import shutil
from app.core.config import get_settings
from app.core.observability import log_json
from app.infrastructure.database import get_db
from app.domain.models import User, Interview, Application, InterviewQuestion, InterviewAnswer, InterviewAnswerVersion, InterviewReport, Job, InterviewReportVersion, InterviewMonitoringEvent
from app.core.timezone import get_ist_now, to_naive_ist
from app.domain.schemas import (
    InterviewStart, InterviewAnswerSubmit, InterviewResponse, 
    InterviewQuestionResponse, InterviewDetailResponse, InterviewReportResponse,
    InterviewListResponse, InterviewAccess, MonitoringEventCreate, MonitoringEventResponse
)



from app.core.auth import get_current_user, get_current_hr, get_current_interview, get_current_interview_any_status, pwd_context, create_access_token
from app.core.ownership import validate_hr_ownership, validate_hr_ownership_for_interview
from app.services.ai_service import (
    generate_adaptive_interview_question,
    evaluate_interview_answer,
    generate_interview_report,
    analyze_introduction,
    evaluate_detailed_answer,
    generate_domain_questions,
    generate_behavioral_question,
    generate_custom_domain_questions_with_meta,
    generate_behavioral_batch,
    extract_questions_from_text,
    transcribe_audio
)
from app.services.resume_parser import parse_content_from_path
from app.services.job_queue import create_job, complete_job, fail_job, get_job, ai_jobs

# Import termination checker (reuse analyzer singleton from ai_service)
try:
    from backend.interview_process.response_analyzer import ResponseAnalyzer as _RA
except ImportError:
    from interview_process.response_analyzer import ResponseAnalyzer as _RA
_termination_checker = _RA()


router = APIRouter(prefix="/api/interviews", tags=["interviews"])
logger = logging.getLogger(__name__)
settings = get_settings()

from app.core.rate_limiter import limiter
from app.core.idempotency import is_duplicate_request
from app.core.ephemeral_result_cache import cache_get as _idem_cache_get, cache_set as _idem_cache_set



async def evaluate_answer_task(
    answer_id: int,
    question_text: str,
    answer_text: str,
    question_type: str,
    interview_id: int
):
    """
    Background task to evaluate an interview answer using AI and handle 
    auto-termination logic without blocking the main request.
    
    Optimized to minimize database write-lock duration during slow AI calls.
    """
    from app.infrastructure.database import SessionLocal
    from sqlalchemy.orm import Session
    from app.services.ai_service import evaluate_detailed_answer

    def fallback_score_answer(rule_answer_text: str, rule_question_text: str) -> float:
        """Rule-based scoring when AI evaluation is unavailable."""
        if not rule_answer_text or len(rule_answer_text.strip()) < 20:
            return 2.0  # too short

        ans_lower = rule_answer_text.lower()
        # Baseline score for any reasonable answer.
        score = 5.0

        length = len(rule_answer_text.split())
        if length > 40:
            score += 1.0
        if length > 80:
            score += 0.5

        keywords = [
            "experience", "implemented", "designed", "led", "built", "improved",
            "debugged", "deployed", "collaborated", "resolved", "optimized",
            "architecture", "api", "database", "performance", "team", "result",
        ]
        matched = sum(1 for k in keywords if k in ans_lower)
        score += min(matched * 0.3, 2.0)

        # Nudge scores if the question appears to be addressed directly.
        q_lower = (rule_question_text or "").lower()
        if q_lower and any(w in ans_lower for w in ["api", "database", "architecture", "performance", "security", "testing"]):
            score += 0.2

        return round(min(max(score, 0.0), 10.0), 1)
    
    # 1. PRE-EVALUATION: The AI call can take 10-20 seconds.
    # Use background tasks for question generation to avoid blocking the main thread.
    is_decryption_failure = False
    if answer_text:
        ans_stripped = answer_text.strip()
        if ans_stripped.startswith("[UNREADABLE]") or ans_stripped.startswith("[DECRYPTION_ERROR]"):
            is_decryption_failure = True

    ai_used = False
    fallback_used = False
    confidence_score = 0.5
    evaluation = None
    last_ai_error = None  # type: ignore[assignment]

    if is_decryption_failure:
        fallback_used = True
        answer_score = 0.0
        technical_score = 0.0
        completeness_score = 0.0
        depth_score = 0.0
        confidence_score = 0.0
        answer_evaluation_json = json.dumps(
            {
                "decryption_failure": True,
                "error": "Decryption failure occurred due to key rotation or corrupted data stream."
            }
        )
    else:
        for attempt in range(1, 4):
            try:
                evaluation = await evaluate_detailed_answer(
                    question_text,
                    answer_text,
                    question_type=question_type or "technical",
                )
                break
            except Exception as e:
                last_ai_error = e
                logger.warning(
                    "ai_evaluate_retry",
                    extra={
                        "answer_id": answer_id,
                        "interview_id": interview_id,
                        "attempt": attempt,
                        "error_preview": str(e)[:240],
                    },
                )
                if attempt < 3:
                    await asyncio.sleep(0.35 * attempt)

        if evaluation is not None:
            ai_used = True

            # Map scores from AI response to model fields with safe defaults
            if question_type == "behavioral":
                technical_score = evaluation.get("relevance", evaluation.get("technical_accuracy", 0))
                completeness_score = evaluation.get("action_impact", evaluation.get("completeness", 0))
                depth_score = evaluation.get("depth", 0)
            else:
                technical_score = evaluation.get("technical_accuracy", evaluation.get("relevance", 0))
                completeness_score = evaluation.get("completeness", evaluation.get("action_impact", 0))
                depth_score = evaluation.get("depth", 0)

            answer_score = evaluation.get("overall", 0)
            # Default to high confidence for AI results, low for fallbacks
            confidence_score = float(evaluation.get("confidence_score", 0.85))
            answer_evaluation_json = json.dumps(evaluation)
        else:
            err = last_ai_error or Exception("unknown")
            logger.error(
                "Background AI evaluation failed after retries: %s",
                err,
                extra={"answer_id": answer_id, "interview_id": interview_id},
            )
            heuristic_score = fallback_score_answer(answer_text, question_text)
            fallback_used = True
            answer_score = heuristic_score
            technical_score = heuristic_score
            completeness_score = heuristic_score
            depth_score = heuristic_score
            confidence_score = 0.35
            answer_evaluation_json = json.dumps(
                {
                    "fallback_scored": True,
                    "heuristic_score": heuristic_score,
                    "error": f"Evaluation failed after retries: {str(err)}",
                }
            )

        # If AI failed to return a score object, evaluation is None (handled above).
        # If it returned a JSON but didn't include 'overall' score, it might be None.
        if answer_score is None:
            heuristic_score = fallback_score_answer(answer_text, question_text)
            fallback_used = True
            answer_score = heuristic_score
            technical_score = heuristic_score
            completeness_score = heuristic_score
            depth_score = heuristic_score
            confidence_score = 0.4
            answer_evaluation_json = json.dumps(
                {
                    "fallback_scored": True,
                    "heuristic_score": heuristic_score,
                    "error": "AI evaluation returned no overall score; applied heuristic fallback",
                }
            )
        else:
            try:
                numeric_answer_score = float(answer_score)
                answer_score = max(0.0, min(10.0, numeric_answer_score))
            except Exception:
                answer_score = 0.0

    # 2. SAVE RESULTS: Use a short-lived transaction specifically for the update.
    db: Session = SessionLocal()
    try:
        # Fetch the records within this specific transaction
        answer = db.query(InterviewAnswer).filter(InterviewAnswer.id == answer_id).with_for_update().first()
        interview = db.query(Interview).filter(Interview.id == interview_id).with_for_update().first()
        
        if not answer or not interview:
            logger.warning(f"Task incomplete: answer_id={answer_id} or interview_id={interview_id} not found during result saving.")
            return

        # Update the answer
        answer.answer_score = float(answer_score)
        answer.skill_relevance_score = float(technical_score)
        answer.technical_score = float(technical_score)
        answer.completeness_score = float(completeness_score)
        answer.depth_score = float(depth_score)
        if is_decryption_failure:
            answer.reasoning = {
                "explanation": "Decryption failure occurred due to key rotation or corrupted data stream. Skipping AI evaluation to prevent unfair candidate penalty."
            }
        else:
            answer.reasoning = {"explanation": evaluation.get("reasoning") if evaluation else "Heuristic fallback evaluation due to AI parsing error."}
        answer.answer_evaluation = answer_evaluation_json
        answer.ai_used = bool(ai_used)
        answer.fallback_used = bool(fallback_used)
        answer.confidence_score = float(max(0.0, min(confidence_score, 1.0)))
        answer.evaluated_at = get_ist_now()
        
        # 3. Low Performance Screening (DEPRECATED: Interviews no longer auto-terminate for poor responses)
        # This block has been removed as per user request to ensure all candidates can complete their session.
        
        # Commit the transaction quickly
        db.commit()
        logger.info(f"Successfully saved evaluation for answer_id={answer_id} in {interview_id}")
        
    except Exception as e:
        logger.error(f"Fatal error saving background evaluation: {e}")
        db.rollback()
    finally:
        db.close()



