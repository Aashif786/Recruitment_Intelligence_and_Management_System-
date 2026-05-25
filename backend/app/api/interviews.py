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



# --- Imported Refactored Services ---
from app.services.interview_generation_service import _load_questions_from_repo_set, check_job_status, background_generate_questions, _set_interview_status, _determine_initial_stage, _enforce_stage, _question_count_for_stage, _generate_aptitude_questions, _generate_first_level_questions, _generate_fallback_questions_direct
from app.services.interview_evaluation_service import evaluate_answer_task
from app.services.interview_reporting_service import _finalize_interview_and_report, _finalize_interview_and_report_internal

async def access_interview(
    request: Request,
    data: InterviewAccess,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Access an interview session securely using a one-time key (Finalized for Production).
    
    Guarantees zero 500 errors by:
    1. Atomic session handling with row-level locking (with_for_update).
    2. Eager loading of relationship graph (Interview -> Application -> Job).
    3. Resilient handling of legacy/missing metadata with safe defaults.
    4. 4-hour secure re-access window for in-progress sessions.
    5. Integrated background task scheduling for question generation.
    """
    try:
        # 1. Verification Phase: Find interviews by cleaned email
        email_clean = data.email.lower().strip()
        
        # Inner join with Application since we filter by email
        interviews = db.query(Interview).join(Interview.application).filter(
            Application.candidate_email == email_clean
        ).options(
            joinedload(Interview.application).load_only(
                Application.id, 
                Application.candidate_email, 
                Application.candidate_name, 
                Application.job_id
            ),
            load_only(
                Interview.id, 
                Interview.access_key_hash, 
                Interview.is_used, 
                Interview.status, 
                Interview.used_at, 
                Interview.expires_at
            )
        ).all()
        
        if not interviews:
            logger.warning(f"Access attempt failed: No interview found for email {email_clean}")
            pwd_context.verify(data.access_key, "$2b$12$XzQyJkG9aBcDeFgHiJkLmOpQrStUvWxYz0123456789abcdefghij")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or access key. Please check your invitation email."
            )
            
        matched_interview = None
        for inv in interviews:
            if pwd_context.verify(data.access_key, inv.access_key_hash):
                matched_interview = inv
                break
                
        if not matched_interview:
            logger.warning(f"Access attempt failed: Invalid access key for email {email_clean}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid email or access key. Please check your invitation email."
            )
        
        # 2. Atomic Startup Phase: Re-fetch with row-level lock to prevent race conditions
        # FIX: We split locking and relationship fetching to avoid PostgreSQL error:
        # "FOR UPDATE cannot be applied to the nullable side of an outer join"
        
        # Query 1: Lock only the interviews table row
        db.query(Interview).filter(
            Interview.id == matched_interview.id
        ).with_for_update().first()
        
        # Query 2: Fetch the full object graph with relationships (no lock needed here)
        interview = db.query(Interview).options(
            joinedload(Interview.application).options(
                joinedload(Application.job),
                load_only(
                    Application.id, 
                    Application.candidate_email, 
                    Application.candidate_name, 
                    Application.job_id
                )
            ),
            load_only(
                Interview.id, Interview.application_id, Interview.status, 
                Interview.is_used, Interview.used_at, Interview.expires_at,
                Interview.started_at, Interview.duration_minutes, Interview.interview_stage,
                Interview.locked_skill
            )
        ).filter(
            Interview.id == matched_interview.id
        ).first()
        
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Interview record vanished during access. Please try again."
            )
        
        current_time = get_ist_now()
        
        # 3. Session State & Expiry Validation
        if interview.is_used:
            is_active = interview.status == "in_progress"
            used_at = interview.used_at
            if used_at:
                used_at = to_naive_ist(used_at)
                session_age = current_time - used_at
            elif interview.started_at:
                started_at = to_naive_ist(interview.started_at)
                session_age = current_time - started_at
            else:
                session_age = timedelta(hours=5) # Terminal age to block expired re-entry
            
            # Allow re-entry ONLY if session is in_progress and started within last 4 hours
            # OR if status is terminal (completed, terminated, cancelled, expired) so they can enter the dynamic page to see the final state.
            if (not is_active or session_age > timedelta(hours=4)) and (interview.status not in ["completed", "terminated", "cancelled", "expired"]):
                logger.warning(f"Access denied: Session {interview.id} is {interview.status} and {session_age} old.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail="This interview link has already been used and the session is no longer active."
                )
            logger.info(f"Resuming or viewing session {interview.id} for {email_clean} (status: {interview.status})")
            
        # Link Expiry Validation
        expires_at = to_naive_ist(interview.expires_at)
        if (not expires_at or expires_at < current_time) and (interview.status not in ["completed", "terminated", "cancelled", "expired"]):
            logger.warning(f"Access link expired for interview {interview.id}. Expires at: {expires_at}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="This interview invitation link has expired."
            )
            
        # 4. Atomic Initialization Logic (if first access)
        if not interview.is_used:
            # Handle relationship resilience for orphaned data
            application = interview.application
            job = application.job if application else None
            
            # Fail-safe initialization BEFORE triggering background tasks
            interview.locked_skill = "general"
            interview.is_used = True
            interview.used_at = current_time
            _set_interview_status(interview, "in_progress")
            
            if job:
                interview.interview_stage = _determine_initial_stage(job)
                # Enforce experience-level flow (e.g., aptitude only for juniors)
                if job.experience_level.lower() != "junior" and interview.interview_stage == STAGE_APTITUDE:
                    interview.interview_stage = STAGE_FIRST_LEVEL
                if not interview.started_at:
                    interview.started_at = current_time
                    interview.duration_minutes = job.duration_minutes or 60
            else:
                # Sensible defaults for missing metadata
                interview.interview_stage = STAGE_FIRST_LEVEL
                interview.started_at = current_time
                interview.duration_minutes = 60
            
            logger.info(f"Initializing NEW interview session: {interview.id}")
            
            # Notify HR Owner
            if application and application.hr_id:
                from app.domain.models import Notification
                db.add(Notification(
                    user_id=application.hr_id,
                    notification_type="INTERVIEW_STARTED",
                    title="Interview Started",
                    message=f"{application.candidate_name} has started the AI interview for {job.title if job else 'the position'}.",
                    related_application_id=application.id,
                    related_interview_id=interview.id
                ))
        
        # 5. Background Question Generation Trigger
        # Check for existing questions to avoid duplicate background processing
        # Important: determine 'ready' based on whether ALL enabled rounds are populated.
        q_rows = db.query(InterviewQuestion).filter(
            InterviewQuestion.interview_id == interview.id
        ).all()
        existing_count = len(q_rows)
        
        # Figure out expected question count to determine "ready" status
        expected_count = 0
        application = interview.application
        job = application.job if application else None
        if job and job.aptitude_enabled:
            expected_count += 10 # Standard 10 aptitude questions
        if job and job.first_level_enabled:
            expected_count += 20 # 15 tech + 5 behav (based on _generate_first_level_questions)
        
        # If no job config, assume at least 1 question is needed
        if expected_count == 0:
            expected_count = 1

        # Generate dynamic lifecycle JWT token based on interview duration
        duration_mins = 60
        if job and hasattr(job, "duration_minutes") and job.duration_minutes:
            duration_mins = job.duration_minutes
        elif hasattr(interview, "duration_minutes") and interview.duration_minutes:
            duration_mins = interview.duration_minutes
            
        token_expiry_delta = max(timedelta(hours=4), timedelta(minutes=duration_mins + 30))
        token = create_access_token(
            data={"sub": str(interview.id), "role": "interview"},
            expires_delta=token_expiry_delta
        )
        
        is_ready = existing_count >= expected_count if existing_count > 0 else False
        
        # Readiness Fail-safe: If expected count is high but we have 0 questions, 
        # force re-generation even if is_ready might be True (e.g. expected_count was 0)
        if existing_count == 0 and expected_count > 0:
            is_ready = False
            logger.warning(f"Interview {interview.id} has 0 questions but expected {expected_count}. Forcing generation.")

        response_data = {
            "access_token": token,
            "token_type": "bearer",
            "interview_id": interview.id,
            "interview_stage": interview.interview_stage,
            "status": "ready" if is_ready else "processing"
        }
        
        # Debug counts
        logger.info(f"Interview {interview.id} access: current_q={existing_count}, expected={expected_count}, ready={is_ready}")

        if not is_ready:
            app_id = interview.application_id
            job_id = interview.application.job_id if interview.application else None
            if app_id and job_id:
                ai_job_id = f"gen_q_{interview.id}"
                response_data["job_id"] = ai_job_id
                # Ensure the task is added to the shared queue safely
                # Use DB-level distributed lock with GlobalSettings to prevent cross-worker duplicate execution
                from app.domain.models import GlobalSettings
                lock_key = f"lock_gen_{interview.id}"
                existing_lock = db.query(GlobalSettings).filter(GlobalSettings.key == lock_key).first()
                
                if existing_lock:
                    logger.info(f"Duplicate question generation avoided via existing DB lock for interview {interview.id}")
                else:
                    try:
                        with db.begin_nested():
                            lock_setting = GlobalSettings(key=lock_key, value="processing")
                            db.add(lock_setting)
                        
                        if ai_job_id not in ai_jobs or ai_jobs[ai_job_id]["status"] == "failed":
                            create_job(ai_job_id)
                            background_tasks.add_task(
                                background_generate_questions, 
                                interview.id, job_id, app_id, ai_job_id
                            )
                    except IntegrityError:
                        logger.info(f"Duplicate question generation avoided via concurrent DB lock insertion for interview {interview.id}")
            else:
                # Trigger direct fallback for incomplete application records
                background_tasks.add_task(_generate_fallback_questions_direct, interview.id)
                response_data["status"] = "ready"
        
        # 6. Final Atomic Commit
        # We commit all session state changes and question generation tasks at once
        db.commit()
        return response_data

    except HTTPException:
        # Re-raise managed FastAPI HTTP exceptions
        raise
    except Exception as e:
        db.rollback()
        # Log full stack trace for internal debugging
        error_msg = f"CRITICAL ERROR in access_interview: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        # Return sanitized error message to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An internal error occurred while accessing the interview. Please try again later."
        )


@router.post("/{interview_id}/generate-test-token")
async def generate_test_token(
    interview_id: int,
    interview_requester: User = Depends(get_current_hr),
    db: Session = Depends(get_db),
):
    """
    TEST-ONLY endpoint: generate a raw access key for an interview.
    This avoids having to bypass bcrypt-hashed keys in automated E2E tests.
    """
    if settings.env == "production":
        raise HTTPException(status_code=403, detail="Test token generation is disabled in production.")

    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview.application:
        validate_hr_ownership(interview.application, interview_requester, resource_name="interview")

    import secrets
    new_key = secrets.token_urlsafe(16)
    interview.access_key_hash = pwd_context.hash(new_key)
    interview.expires_at = get_ist_now() + timedelta(days=10)
    interview.is_used = False
    _set_interview_status(interview, "not_started")
    interview.used_at = None

    # Cascade delete previous test answers, questions, and monitoring events for pristine test isolation
    db.query(InterviewAnswer).filter(InterviewAnswer.interview_id == interview_id).delete(synchronize_session=False)
    db.query(InterviewQuestion).filter(InterviewQuestion.interview_id == interview_id).delete(synchronize_session=False)
    db.query(InterviewMonitoringEvent).filter(InterviewMonitoringEvent.interview_id == interview_id).delete(synchronize_session=False)

    db.commit()

    # Raw key is intentionally returned only for non-production environments.
    return {"interview_id": interview_id, "access_key": new_key}


@router.post("/{interview_id}/start")
async def start_interview_session(
    interview_id: int,
    data: InterviewStart,
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db),
):
    """
    Explicitly mark the interview as started (idempotent). Used by the
    /interview/[id] UI after fullscreen before questions are shown.

    The access flow may already set `in_progress` and `started_at`; this
    endpoint is safe to call again when the session is already active.
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not data.camera_active or not data.mic_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera and Microphone access are mandatory to start the interview."
        )

    interview = db.query(Interview).options(
        joinedload(Interview.application).joinedload(Application.job)
    ).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    if interview.status in ("completed", "terminated", "cancelled", "expired"):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This interview has already ended or cannot be started.",
        )

    now = get_ist_now()

    if interview.status == "not_started":
        application = interview.application
        job = application.job if application else None
        interview.is_used = True
        interview.used_at = now
        _set_interview_status(interview, "in_progress")
        if job:
            interview.interview_stage = _determine_initial_stage(job)
            exp = (job.experience_level or "").lower()
            if exp != "junior" and interview.interview_stage == STAGE_APTITUDE:
                interview.interview_stage = STAGE_FIRST_LEVEL
            interview.started_at = now
            interview.duration_minutes = job.duration_minutes or 60
        else:
            interview.interview_stage = STAGE_FIRST_LEVEL
            interview.started_at = now
            interview.duration_minutes = 60
        db.commit()
        db.refresh(interview)
    elif interview.status == "in_progress":
        if not interview.started_at:
            interview.started_at = now
            if not interview.duration_minutes:
                job = interview.application.job if interview.application else None
                interview.duration_minutes = (job.duration_minutes or 60) if job else 60
            db.commit()
            db.refresh(interview)
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interview cannot be started in current state: {interview.status}",
        )

    return {
        "ok": True,
        "status": interview.status,
        "started_at": interview.started_at.isoformat() if interview.started_at else None,
        "duration_minutes": interview.duration_minutes or 60,
    }


@router.get("/{interview_id}/stage")
async def get_interview_stage(
    interview_id: int,
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db)
):
    """Get the current pipeline stage for the interview (Robust with Readiness Checks)."""
    try:
        if interview_session.id != interview_id:
            logger.warning(f"Session mismatch: token session {interview_session.id} vs requested {interview_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
        # Ensure relationships are loaded if not already present
        # get_current_interview_any_status might return a session-cached object; 
        # we ensure application and job are available without lazy-load failures.
        interview = interview_session
        if not hasattr(interview, 'application') or interview.application is None:
            # Fallback re-fetch if relationship is detached or missing
            interview = db.query(Interview).options(
                joinedload(Interview.application).joinedload(Application.job)
            ).filter(Interview.id == interview_id).first()
            
            if not interview:
                logger.error(f"Interview {interview_id} record vanished during stage fetch")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")

        # ── READINESS CHECK ──
        # Check if questions exist for the current stage (unless stage is COMPLETED)
        questions_ready = True
        if interview.status == "in_progress" and interview.interview_stage != STAGE_COMPLETED:
            questions_count = _question_count_for_stage(db, interview_id, interview.interview_stage)
            questions_ready = questions_count > 0

            if not questions_ready:
                # Questions aren't ready yet.
                logger.info(f"Session {interview_id} load: stage '{interview.interview_stage}' questions not ready yet. Returning 202.")
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "id": interview.id,
                        "status": "processing",
                        "message": "Preparing your custom interview questions. Please wait...",
                        "interview_stage": interview.interview_stage,
                        "questions_ready": False,
                    }
                )

        # Safely handle potential nulls in relationship graph
        application = getattr(interview, 'application', None)
        job = getattr(application, 'job', None) if application else None
        
        return {
            "id": interview.id,
            "status": interview.status,
            "interview_stage": interview.interview_stage or STAGE_FIRST_LEVEL,
            "locked_skill": interview.locked_skill or "general",
            "total_questions": interview.total_questions or 0,
            "aptitude_enabled": getattr(job, 'aptitude_enabled', False) if job else False,
            "first_level_enabled": getattr(job, 'first_level_enabled', True) if job else True,
            "aptitude_score": getattr(interview, 'aptitude_score', None),
            "aptitude_completed_at": getattr(interview, 'aptitude_completed_at', None),
            "started_at": getattr(interview, 'started_at', None),
            "duration_minutes": getattr(interview, 'duration_minutes', 60) or 60,
            "questions_ready": questions_ready,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CRITICAL Error loading stage for session {interview_id}: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="An internal error occurred while loading your session.")



@router.get("/{interview_id}/questions")
async def get_all_questions(
    interview_id: int,
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db)
):
    """Get ALL questions for the interview (all stages)."""
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # ── READINESS CHECK ──
    # If session is in-progress and questions aren't ready for the current stage, return 202
    if interview_session.status == "in_progress" and interview_session.interview_stage != STAGE_COMPLETED:
        stage = interview_session.interview_stage or STAGE_FIRST_LEVEL
        if _question_count_for_stage(db, interview_id, stage) == 0:
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "id": interview_id,
                    "status": "processing",
                    "message": "Preparing your interview questions. Please wait...",
                    "questions_ready": False,
                }
            )

    # Filter by stage to prevent leaking future questions to candidates
    query = db.query(InterviewQuestion).filter(
        InterviewQuestion.interview_id == interview_id
    )
    if interview_session.status == "in_progress":
        if interview_session.interview_stage == STAGE_APTITUDE:
            query = query.filter(InterviewQuestion.question_type == "aptitude")
        elif interview_session.interview_stage == STAGE_FIRST_LEVEL:
            query = query.filter(InterviewQuestion.question_type != "aptitude")
    
    questions = query.order_by(InterviewQuestion.question_number).all()

    # Batch-load answered status
    question_ids = [q.id for q in questions]
    answers = (
        db.query(InterviewAnswer).filter(InterviewAnswer.question_id.in_(question_ids)).all()
        if question_ids
        else []
    )
    answered_ids = {a.question_id for a in answers}
    ans_by_q = {a.question_id: a for a in answers}

    result = []
    for q in questions:
        ans = ans_by_q.get(q.id)
        evaluated_at = ans.evaluated_at.isoformat() if ans and ans.evaluated_at else None
        result.append({
            "id": q.id,
            "interview_id": q.interview_id,
            "question_number": q.question_number,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "question_options": q.options,
            "is_answered": q.id in answered_ids,
            "evaluated_at": evaluated_at,
            "answer_score": float(ans.answer_score) if ans and ans.answer_score is not None else None,
            "evaluation_pending": bool(ans and ans.evaluated_at is None),
            "answer_text": ans.answer_text if ans else None,
        })
    return result


@router.get("/{interview_id}/current-question", response_model=InterviewQuestionResponse)
async def get_current_question(
    interview_id: int,
    interview_session: Interview = Depends(get_current_interview),
    db: Session = Depends(get_db)
):
    """Get current unanswered question for the current stage."""
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    interview = interview_session
    
    if interview.interview_stage == STAGE_COMPLETED:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Interview fully completed")

    if interview.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Interview complete")
    
    # ── READINESS CHECK ──
    # If session is in-progress and questions aren't ready for the current stage, return 202
    stage = interview.interview_stage or STAGE_FIRST_LEVEL
    if _question_count_for_stage(db, interview_id, stage) == 0:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "id": interview_id,
                "status": "processing",
                "message": "Preparing your interview questions. Please wait...",
                "questions_ready": False,
            }
        )

    # Filter by current stage
    query = db.query(InterviewQuestion).filter(
        InterviewQuestion.interview_id == interview_id
    )
    if interview.interview_stage == STAGE_APTITUDE:
        query = query.filter(InterviewQuestion.question_type == "aptitude")
    else:
        query = query.filter(InterviewQuestion.question_type != "aptitude")
    
    questions = query.order_by(InterviewQuestion.question_number).all()
    
    # Batch-load answered IDs in ONE query (eliminates N+1)
    question_ids = [q.id for q in questions]
    answered_ids = set(
        row[0] for row in db.query(InterviewAnswer.question_id).filter(
            InterviewAnswer.question_id.in_(question_ids)
        ).all()
    ) if question_ids else set()
    
    for question in questions:
        if question.id not in answered_ids:
            # Manually map to schema to avoid AttributeError if model lacks question_options
            return {
                "id": question.id,
                "interview_id": question.interview_id,
                "question_number": question.question_number,
                "question_text": question.question_text,
                "question_type": question.question_type,
                "question_options": question.options,
                "options": question.options
            }
            
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="All questions in this stage answered")


# ─── Background Tasks ─────────────────────────────────────────────────────────

@router.post("/{interview_id}/submit-answer")
@limiter.limit("60/minute")
async def submit_answer(
    request: Request,
    interview_id: int,
    data: InterviewAnswerSubmit,
    background_tasks: BackgroundTasks,
    interview_session: Interview = Depends(get_current_interview),
    db: Session = Depends(get_db)
):
    """Submit answer to current question (stage-aware)."""
    request_id_header = request.headers.get("X-Request-ID")
    if settings.enable_request_id_idempotency and is_duplicate_request(
        request_id=request_id_header,
        scope="interviews.submit_answer",
        key=f"{interview_id}:{data.question_id}",
        ttl_seconds=120,
    ):
        existing = db.query(InterviewAnswer).filter(
            InterviewAnswer.question_id == data.question_id,
            InterviewAnswer.interview_id == interview_id
        ).first()
        if existing:
            return {"success": True, "answer_id": existing.id, "idempotent_replay": True}
        raise HTTPException(status_code=409, detail="Duplicate submit request detected. Please retry.")

    # 1. Access Control: Ensure the session belongs to the current candidate
    if interview_session.id != interview_id:
        logger.warning(f"Unauthorized access attempt: Session {interview_session.id} tried to submit for {interview_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Session mismatch.")

    # 2. Re-read with row-level lock to prevent race conditions during submission
    try:
        interview = db.query(Interview).filter(
            Interview.id == interview_id
        ).with_for_update().first()
        
        if not interview:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found.")
            
        if interview.status != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail=f"Interview submission blocked: Session is in {interview.status} state."
            )

        # ── TIMER VALIDATION ──
        if interview.started_at and interview.duration_minutes:
            now = get_ist_now()
            # Naive to aware conversion if needed, but get_ist_now usually returns naive for this project
            # based on my previous analysis of to_naive_ist usage.
            # Let's check if started_at is naive or aware.
            start_time = to_naive_ist(interview.started_at)
            # Based on app/core/timezone.py usage in the file, it seems they use naive IST.
            end_time = start_time + timedelta(minutes=interview.duration_minutes)
            
            # Adding a 2-minute grace period for network latency during the final submission
            if now > (end_time + timedelta(minutes=2)):
                logger.warning(f"Submission rejected: Timer expired for interview {interview_id}. End time: {end_time}, Now: {now}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Interview session has expired. Submissions are no longer accepted for this session."
                )

        if interview.interview_stage == STAGE_COMPLETED:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Interview is already fully completed")

        # 3. Validate Question ID (Moved before proctoring check to avoid NameError)
        current_question = db.query(InterviewQuestion).filter(
            InterviewQuestion.id == data.question_id,
            InterviewQuestion.interview_id == interview_id
        ).first()
        
        if not current_question:
            logger.warning(
                "validation_failed",
                extra={"service_module": "interviews", "field": "question_id", "reason": "not_found_in_session", "input_preview": str(data.question_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found in this session."
            )

        # ── PROCTORING ENFORCEMENT ──
        # If the job requires AI/Mixed mode, we expect monitoring events to be flowing.
        # We check if at least one 'normal' or 'focus_lost' event exists if the session 
        # has been active for more than 45 seconds.
        job = interview.application.job if interview.application else None
        if job and job.interview_mode in ["ai", "mixed"] and current_question.question_type != "aptitude":
            active_duration = get_ist_now() - to_naive_ist(interview.started_at)
            if active_duration > timedelta(seconds=45):
                from sqlalchemy import exists
                has_events = db.query(exists().where(
                    InterviewMonitoringEvent.interview_id == interview_id
                )).scalar()
                
                if not has_events:
                    logger.error(f"Proctoring Bypass Detected: No monitoring events for interview {interview_id} after {active_duration.seconds}s.")
                    # We don't terminate immediately to avoid false positives, but we block the submission
                    # until the proctoring engine checks in.
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Proctoring system is offline. Please ensure your camera is visible and refresh the page."
                    )
            
        # 3.5. Granular Validation of Answer Text
        answer_len = len(data.answer_text or "")
        if answer_len > 10000:
            logger.warning(f"Extremely long answer detected for interview {interview_id}: {answer_len} chars")
        
        # Reject empty or purely whitespace answers for non-aptitude questions
        if (current_question.question_type or "").lower() != "aptitude":
            if not data.answer_text or not data.answer_text.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Answer cannot be empty. Please provide a response."
                )
            if len(data.answer_text.strip()) < 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Your answer is too short. Please provide a more detailed response."
                )
        

        # Resolve answer text early for idempotency check and saving
        stored_answer_text = data.answer_text
        if (current_question.question_type or "").lower() == "aptitude" and current_question.options:
            try:
                options = json.loads(current_question.options)
                if isinstance(options, list) and len(options) > 0:
                    submitted_val = data.answer_text.strip().upper()
                    resolved_idx = -1
                    
                    # Case 1: Simple digit index (0, 1, 2...)
                    if submitted_val.isdigit():
                        resolved_idx = int(submitted_val)
                    # Case 2: Letter index (A, B, C...)
                    elif len(submitted_val) == 1 and 'A' <= submitted_val <= 'Z':
                        resolved_idx = ord(submitted_val) - ord('A')
                    # Case 3: "Option A", "Choice B" etc.
                    elif any(submitted_val.startswith(p) for p in ["OPTION ", "CHOICE "]):
                        last_char = submitted_val[-1]
                        if 'A' <= last_char <= 'Z':
                            resolved_idx = ord(last_char) - ord('A')
                        elif last_char.isdigit():
                            resolved_idx = int(last_char)

                    if 0 <= resolved_idx < len(options):
                        stored_answer_text = str(options[resolved_idx])
                        logger.info(f"Resolved aptitude input '{data.answer_text}' to text during check for session {interview_id}: {stored_answer_text}")
            except Exception as e:
                logger.warning(f"Failed to resolve aptitude input during check for session {interview_id}: {e}")

        # 4. Check if answer exists (we will update it instead of rejecting)
        existing_answer = db.query(InterviewAnswer).filter(
            InterviewAnswer.question_id == data.question_id,
            InterviewAnswer.interview_id == interview_id
        ).first()
        
        if existing_answer and existing_answer.evaluated_at:
             # Idempotent replay: if they resubmitted the exact same raw or resolved text, return success
             if existing_answer.answer_text == stored_answer_text or existing_answer.answer_text == data.answer_text:
                 logger.info(f"Idempotent resubmission of already evaluated answer for question {data.question_id} in interview {interview_id}")
                 return {"success": True, "answer_id": existing_answer.id, "idempotent_replay": True}
             
             # If it was already evaluated and is different, we don't allow overwriting to prevent race conditions/cheating
             logger.warning(f"Submission rejected: Answer for question {data.question_id} in interview {interview_id} was already evaluated.")
             raise HTTPException(
                 status_code=status.HTTP_409_CONFLICT,
                 detail="This question has already been evaluated and cannot be modified."
             )
        
        # 5. Termination Protocol (Abusive language / Explicit quit)
        should_terminate = False
        termination_reason = ""
        # Only run for technical/behavioral — aptitude answers are MCQs or very short
        if (current_question.question_type or "").lower() != "aptitude":
            try:
                # Sanitize input before termination check
                from app.services.ai_service import sanitize_ai_input
                sanitized_answer = sanitize_ai_input(data.answer_text, log_context=f"Interview {interview_id}")
                
                # Check for termination keywords (case-insensitive & robust)
                should_terminate, termination_reason = _termination_checker.check_for_termination(
                    sanitized_answer, 
                    question_type=current_question.question_type
                )
            except Exception as e:
                logger.error(f"Termination checker error: {e}")
                should_terminate = False

        if should_terminate:
            try:
                _set_interview_status(interview, "terminated")
                interview.interview_stage = STAGE_COMPLETED
                interview.ended_at = get_ist_now()
                
                from app.services.state_machine import CandidateStateMachine, TransitionAction
                from app.domain.models import InterviewIssue
                
                fsm = CandidateStateMachine(db)
                try:
                    fsm.transition(interview.application, TransitionAction.REJECT, notes=f"Interview automatically terminated. Reason: {termination_reason}")
                except Exception as e:
                    logger.error(f"FSM Transition error during termination: {e}")
                    interview.application.status = "rejected"
                
                # Create a ticket for HR review
                system_issue = InterviewIssue(
                    interview_id=interview.id,
                    candidate_name=interview.application.candidate_name,
                    candidate_email=interview.application.candidate_email,
                    issue_type="misconduct_appeal" if termination_reason == "misconduct" else "technical",
                    description=f"SYSTEM AUTO-TERMINATION: {termination_reason}. Input snippet: {data.answer_text[:100]}...",
                    status="pending"
                )
                db.add(system_issue)
                db.commit()
                
                # Pre-generate report for terminated session
                background_tasks.add_task(_finalize_interview_and_report, interview_id)

                return {
                    "success": True,
                    "terminated": True,
                    "termination_reason": termination_reason,
                    "idempotent_replay": False,
                    "message": (
                        "Interview terminated due to inappropriate language."
                        if termination_reason == "misconduct"
                        else "Interview ended at your request."
                    )
                }
            except Exception as e:
                db.rollback()
                logger.error(f"Termination protocol failed: {e}")
                raise HTTPException(status_code=500, detail="Internal failure during termination protocol.")

        # 6. Save Answer
        try:
            # stored_answer_text has already been resolved and validated above
            pass

            if existing_answer:
                # ── Phase 7: Answer Versioning ──
                try:
                    version_count = db.query(InterviewAnswerVersion).filter(InterviewAnswerVersion.answer_id == existing_answer.id).count()
                    old_version = InterviewAnswerVersion(
                        answer_id=existing_answer.id,
                        answer_text=existing_answer.answer_text,
                        answer_score=existing_answer.answer_score,
                        submitted_at=existing_answer.submitted_at or get_ist_now(),
                        version_number=version_count + 1
                    )
                    db.add(old_version)
                    db.flush()
                except Exception as e:
                    logger.warning(f"Failed to version old interview answer: {e}")

                existing_answer.answer_text = stored_answer_text
                existing_answer.submitted_at = get_ist_now()
                # reset evaluation so it gets re-evaluated
                existing_answer.answer_score = None
                existing_answer.skill_relevance_score = None
                existing_answer.answer_evaluation = None
                existing_answer.evaluated_at = None
                answer = existing_answer
            else:
                answer = InterviewAnswer(
                    question_id=current_question.id,
                    interview_id=interview_id,
                    answer_text=stored_answer_text,
                    submitted_at=get_ist_now()
                )

            # Auto-grade aptitude MCQs
            if current_question.question_type == "aptitude" and current_question.correct_answer is not None:
                submitted_val = data.answer_text.strip()
                correct_ans_str = current_question.correct_answer.strip()
                is_correct = False
                
                # 1. Direct text check (case-insensitive)
                if submitted_val.lower() == correct_ans_str.lower():
                    is_correct = True
                
                # 2. Resolve letter to index (A=0, B=1, ...) or direct digit
                if not is_correct:
                    submitted_as_int = None
                    if submitted_val.isdigit():
                        submitted_as_int = int(submitted_val)
                    elif len(submitted_val) == 1 and submitted_val.upper() in "ABCDEFGHIJ":
                        submitted_as_int = ord(submitted_val.upper()) - ord("A")
                    
                    correct_idx = None
                    # Try parsing correct_answer as float then int
                    try:
                        correct_as_float = float(correct_ans_str)
                        if correct_as_float.is_integer():
                            correct_idx = int(correct_as_float)
                    except (ValueError, TypeError):
                        pass
                    
                    # Or try parsing correct_answer as letter index
                    if correct_idx is None:
                        if len(correct_ans_str) == 1 and correct_ans_str.upper() in "ABCDEFGHIJ":
                            correct_idx = ord(correct_ans_str.upper()) - ord("A")
                            
                    if correct_idx is not None and submitted_as_int is not None and submitted_as_int == correct_idx:
                        is_correct = True

                # 3. Option lookup check
                if not is_correct and current_question.options:
                    try:
                        options = json.loads(current_question.options)
                        if isinstance(options, list):
                            # Try parsing correct answer as index
                            correct_idx = None
                            try:
                                correct_as_float = float(correct_ans_str)
                                if correct_as_float.is_integer():
                                    correct_idx = int(correct_as_float)
                            except (ValueError, TypeError):
                                pass
                            
                            if correct_idx is not None and correct_idx < len(options):
                                if submitted_val.lower() == options[correct_idx].lower():
                                    is_correct = True
                            # Also check if correct_ans_str matches one of the option texts, and submitted_val matches its index
                            elif submitted_as_int is not None and submitted_as_int < len(options):
                                if options[submitted_as_int].lower() == correct_ans_str.lower():
                                    is_correct = True
                    except Exception:
                        pass
                
                answer.answer_score = 10.0 if is_correct else 0.0
                answer.skill_relevance_score = 10.0 if is_correct else 0.0
                answer.evaluated_at = get_ist_now()
                answer.answer_evaluation = json.dumps({"auto_graded": True, "is_correct": is_correct})

            # Record monitoring event for answer submission
            try:
                monitoring_event = InterviewMonitoringEvent(
                    interview_id=interview_id,
                    event_type="answer_submitted",
                    confidence_score=1.0,
                    timestamp=get_ist_now()
                )
                db.add(monitoring_event)
            except Exception as e:
                logger.warning(f"Failed to record monitoring event for interview {interview_id}: {e}")

            if not existing_answer:
                db.add(answer)
            db.commit()
            db.refresh(answer)
        except IntegrityError:
            db.rollback()
            existing = db.query(InterviewAnswer).filter(
                InterviewAnswer.question_id == current_question.id,
                InterviewAnswer.interview_id == interview_id
            ).first()
            if existing:
                return {"success": True, "answer_id": existing.id, "idempotent_replay": True}
            raise HTTPException(status_code=409, detail="Answer already exists for this question.")
        except Exception as e:
            db.rollback()
            logger.error(f"Answer save error: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save answer safely.")

        # 7. Background AI Evaluation
        if current_question.question_type != "aptitude":
            background_tasks.add_task(
                evaluate_answer_task,
                answer.id,
                current_question.question_text,
                data.answer_text,
                current_question.question_type or "technical",
                interview_id
            )

        return {"success": True, "answer_id": answer.id, "idempotent_replay": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unhandled submission error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="A critical server error occurred during submission.")


@router.post("/{interview_id}/complete-aptitude")
async def complete_aptitude(
    interview_id: int,
    interview_session: Interview = Depends(get_current_interview),
    db: Session = Depends(get_db)
):
    """
    Complete the aptitude round and automatically transition to first-level interview.
    Calculates aptitude score, generates first-level questions, and returns the first question.
    NO re-login required — same session continues.
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Re-read with row-level lock to prevent double-click race
    interview = db.query(Interview).filter(
        Interview.id == interview_id
    ).with_for_update().first()
    
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
        
    if interview.interview_stage == STAGE_COMPLETED:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Interview is already fully completed")
        
    if interview.status != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=f"Action blocked: Session is in {interview.status} state."
        )
    
    # Idempotency guard: if already past aptitude, return success
    if interview.interview_stage != STAGE_APTITUDE:
        return {
            "success": True,
            "aptitude_score": interview.aptitude_score,
            "new_stage": interview.interview_stage,
            "message": "Aptitude round already completed.",
        }
    
    _enforce_stage(interview, STAGE_APTITUDE)

    # Verify all aptitude questions are answered — batch query (no N+1)
    aptitude_questions = db.query(InterviewQuestion).filter(
        InterviewQuestion.interview_id == interview_id,
        InterviewQuestion.question_type == "aptitude"
    ).all()

    apt_q_ids = [q.id for q in aptitude_questions]
    answered_q_ids = set()
    if apt_q_ids:
        answered = db.query(InterviewAnswer.question_id).filter(
            InterviewAnswer.question_id.in_(apt_q_ids)
        ).all()
        answered_q_ids = {row[0] for row in answered}

    unanswered = [q for q in aptitude_questions if q.id not in answered_q_ids]
    if unanswered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All aptitude questions must be answered before completing the aptitude round."
        )

    # Calculate aptitude score for display purposes (does not affect final combined score)
    answers = db.query(InterviewAnswer).filter(
        InterviewAnswer.question_id.in_(apt_q_ids)
    ).all() if apt_q_ids else []
    
    apt_scores = [a.answer_score for a in answers if a.answer_score is not None]
    if apt_scores:
        interview.aptitude_score = sum(apt_scores) / len(apt_scores)
    else:
        interview.aptitude_score = 0.0

    interview.aptitude_completed_at = get_ist_now()
    interview.aptitude_completed = True

    if not interview.application or not interview.application.job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Job associated with this interview could not be found."
        )
    job = interview.application.job

    # Check if first_level is enabled
    if job.first_level_enabled:
        try:
            # Transition to first-level interview
            # Questions were PRE-GENERATED during access_interview — no AI delay here
            interview.interview_stage = STAGE_FIRST_LEVEL
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed changing pipeline stages.")

        # Get the first question to return
        first_q = db.query(InterviewQuestion).filter(
            InterviewQuestion.interview_id == interview_id,
            InterviewQuestion.question_type != "aptitude"
        ).order_by(InterviewQuestion.question_number).first()

        return {
            "success": True,
            "aptitude_score": interview.aptitude_score,
            "new_stage": STAGE_FIRST_LEVEL,
            "message": "Aptitude round completed. First-level interview questions generated.",
            "first_question": {
                "id": first_q.id,
                "question_number": first_q.question_number,
                "question_text": first_q.question_text,
                "question_type": first_q.question_type,
            } if first_q else None,
        }
    else:
        try:
            # Aptitude only — mark as completed
            interview.interview_stage = STAGE_COMPLETED
            _set_interview_status(interview, "completed")
            interview.ended_at = get_ist_now()
            interview.overall_score = interview.aptitude_score
            # Use FSM for state transition: ai_interview -> interview_completed
            from app.services.state_machine import CandidateStateMachine, TransitionAction
            fsm = CandidateStateMachine(db)
            try:
                fsm.transition(interview.application, TransitionAction.SYSTEM_INTERVIEW_COMPLETE)
            except Exception:
                interview.application.status = "interview_completed"
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to finalise aptitude round.")

        # Generate minimal InterviewReport for aptitude-only jobs
        try:
            existing_report = db.query(InterviewReport).filter(
                InterviewReport.interview_id == interview_id
            ).first()
            if not existing_report:
                report = InterviewReport(
                    interview_id=interview_id,
                    application_id=interview.application.id,
                    job_id=job.id,
                    candidate_name=interview.application.candidate_name,
                    candidate_email=interview.application.candidate_email,
                    applied_role=job.title,
                    overall_score=interview.aptitude_score or 0.0,
                    technical_skills_score=0,
                    communication_score=0,
                    problem_solving_score=0,
                    strengths="[]",
                    weaknesses="[]",
                    summary="Aptitude-only interview completed. No first-level interview configured.",
                    recommendation="consider",
                    detailed_feedback="Aptitude round completed successfully.",
                    aptitude_score=interview.aptitude_score,
                    combined_score=interview.aptitude_score or 0.0,
                    ai_used=False,
                    fallback_used=False,
                    confidence_score=0.0,
                )
                db.add(report)
                db.commit()
        except Exception as e:
            logger.error(f"Error creating aptitude-only report: {e}")

        return {
            "success": True,
            "aptitude_score": interview.aptitude_score,
            "new_stage": STAGE_COMPLETED,
            "message": "Aptitude round completed. No first-level interview configured for this job.",
        }



@router.post("/{interview_id}/fail-device-test")
async def fail_device_test(
    interview_id: int,
    background_tasks: BackgroundTasks,
    data: dict = Body(...),
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db),
):
    """
    Invalidates access keys and deactivates the session immediately if a candidate
    fails or attempts to bypass device hardware verification.
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    interview = db.query(Interview).filter(
        Interview.id == interview_id
    ).with_for_update().first()

    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    reason = (data.get("reason") or "").strip() or "Failed device hardware verification"
    logger.warning(f"DEVICE_TEST_VIOLATION: Terminating interview {interview_id}. Reason: {reason}")

    # 1. Clear access key hash completely to make it permanently invalid
    interview.access_key_hash = None

    # 2. Terminate interview session state
    _set_interview_status(interview, "terminated")
    interview.interview_stage = STAGE_COMPLETED
    interview.ended_at = get_ist_now()

    # 3. Transition candidate state machine to REJECT
    try:
        from app.services.state_machine import CandidateStateMachine, TransitionAction
        if interview.application:
            fsm = CandidateStateMachine(db)
            fsm.transition(
                interview.application,
                TransitionAction.REJECT,
                notes=f"Interview auto-terminated by proctoring system. Reason: {reason}",
            )
    except Exception as fsm_err:
        logger.error(f"FSM transition failed on device test violation: {fsm_err}")

    db.commit()

    if background_tasks:
        background_tasks.add_task(_finalize_interview_and_report, interview_id)

    return {"ok": True, "terminated": True, "access_key_invalidated": True, "reason": reason}



@router.post("/{interview_id}/security-violation")
async def report_security_violation(
    interview_id: int,
    background_tasks: BackgroundTasks,
    data: dict = Body(...),
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db),
):
    """
    Report a proctoring security violation (tab switch, face not detected, multiple people, etc.)
    Used by the frontend proctoring engine as a REST replacement for the WS security_violation action.
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Normalise empty/whitespace reasons so the default is always recorded
    reason = (data.get("reason") or "").strip() or "Proctoring violation"
    logger.warning(f"SECURITY_VIOLATION: Terminating interview {interview_id}. Reason: {reason}")

    interview = db.query(Interview).filter(
        Interview.id == interview_id
    ).with_for_update().first()

    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    if interview.status in ("terminated", "completed", "cancelled") or interview.interview_stage == STAGE_COMPLETED:
        return {"ok": True, "already_ended": True, "status": interview.status}

    _set_interview_status(interview, "terminated")
    interview.interview_stage = STAGE_COMPLETED
    interview.ended_at = get_ist_now()

    # FSM transition: reject the application
    try:
        from app.services.state_machine import CandidateStateMachine, TransitionAction
        if interview.application:
            fsm = CandidateStateMachine(db)
            fsm.transition(
                interview.application,
                TransitionAction.REJECT,
                notes=f"Interview auto-terminated by proctoring system. Reason: {reason}",
            )
    except Exception as fsm_err:
        logger.error(f"FSM transition failed on security violation: {fsm_err}")

    db.commit()

    # Generate final report in background
    if background_tasks:
        background_tasks.add_task(_finalize_interview_and_report, interview_id)

    return {"ok": True, "terminated": True, "reason": reason}


@router.post("/{interview_id}/end")
async def end_interview(
    request: Request,
    interview_id: int,
    background_tasks: BackgroundTasks,
    data: dict = Body(None),
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db)
):
    """End interview manually (standard path).

    Returns immediately - AI report generation runs in a background task.
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    request_id_header = request.headers.get("X-Request-ID")
    if settings.enable_request_id_idempotency and is_duplicate_request(
        request_id=request_id_header,
        scope="interviews.end",
        key=str(interview_id),
        ttl_seconds=120,
    ):
        interview_dup = db.query(Interview).filter(Interview.id == interview_id).first()
        if interview_dup and interview_dup.status != "in_progress":
            return {
                "success": True,
                "message": f"Interview is already in {interview_dup.status} state.",
                "status": interview_dup.status,
                "interview_id": interview_id,
                "interview_score": interview_dup.overall_score,
                "combined_score": interview_dup.overall_score,
            }

    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id)
        .with_for_update()
        .first()
    )

    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    if interview.status != "in_progress":
        return {
            "success": True,
            "message": f"Interview is already in {interview.status} state.",
            "status": interview.status,
            "interview_id": interview_id,
            "interview_score": interview.overall_score,
            "combined_score": interview.overall_score,
        }

    # 1. Enforcement Check (Ensure sufficient answers if not already terminated or forced)
    is_forced = isinstance(data, dict) and data.get("force") is True
    ended_early = isinstance(data, dict) and data.get("ended_early") is True
    if interview.status != "terminated" and not is_forced:
        if interview.interview_stage == STAGE_APTITUDE:
            questions = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id == interview_id,
                InterviewQuestion.question_type == "aptitude"
            ).all()
        else:
            questions = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id == interview_id,
                InterviewQuestion.question_type != "aptitude"
            ).all()
        question_ids = [q.id for q in questions]
        # Count answers by joining through question_id to avoid NULL interview_id issues
        answered_count = db.query(InterviewAnswer).filter(
            InterviewAnswer.question_id.in_(question_ids)
        ).count() if question_ids else 0

        if answered_count < len(questions) and len(questions) > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Please answer all questions before ending. Missing: {len(questions) - answered_count}"
            )

    # 1.5 Handle termination reason if provided (proctoring violations etc.)
    if data and data.get("termination_reason"):
        from app.domain.models import InterviewIssue
        reason = data["termination_reason"]
        logger.warning(f"Manual termination requested for interview {interview_id}: {reason}")
        _set_interview_status(interview, "terminated")
        issue = InterviewIssue(
            interview_id=interview_id,
            candidate_name=interview.application.candidate_name if interview.application else "Candidate",
            candidate_email=interview.application.candidate_email if interview.application else "Email N/A",
            issue_type="proctoring",
            description=reason,
            status="resolved"
        )
        db.add(issue)
        db.commit()

    # 1.6 Annotate hr_notes when the candidate deliberately ends the interview early
    if (ended_early or is_forced) and interview.application:
        now_str = get_ist_now().strftime("%Y-%m-%d %H:%M UTC")
        early_note = (
            f"[{now_str}] Candidate ended the interview early using the 'End Early' button "
            "before completing all questions."
        )
        existing_notes = interview.application.hr_notes or ""
        interview.application.hr_notes = (
            (existing_notes.rstrip() + "\n" + early_note).strip()
            if existing_notes
            else early_note
        )
        db.commit()

    # 2. Mark state immediately so the frontend sees a finished interview right away.
    if interview.status == "in_progress":
        _set_interview_status(interview, "completed")
    interview.interview_stage = STAGE_COMPLETED
    if not interview.ended_at:
        interview.ended_at = get_ist_now()
    db.commit()

    # 3. Run the heavy AI report generation in the background so this response
    #    returns in milliseconds instead of blocking for 20-60 seconds.
    background_tasks.add_task(_finalize_interview_and_report, interview_id)
    logger.info(f"Interview {interview_id} ended — report generation queued as background task.")

    return {
        "success": True,
        "interview_id": interview_id,
        "status": interview.status,
        "interview_score": interview.overall_score,
        "combined_score": interview.overall_score,
    }

@router.post("/{interview_id}/abandon")
async def abandon_interview(
    interview_id: int,
    background_tasks: BackgroundTasks,
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db)
):
    """
    Called when a candidate closes the tab or abandons the interview.
    Forcefully terminates the interview and generates a report.
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    interview = db.query(Interview).filter(Interview.id == interview_id).with_for_update().first()
    
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
        
    if interview.status != "in_progress" or interview.interview_stage == STAGE_COMPLETED:
        return {"success": True, "message": f"Interview is already in {interview.status} state."}

    try:
        # Mark as terminated
        _set_interview_status(interview, "terminated")
        interview.interview_stage = STAGE_COMPLETED
        interview.ended_at = get_ist_now()
        
        # Track abandonment in Issue list
        from app.domain.models import InterviewIssue
        system_issue = InterviewIssue(
            interview_id=interview.id,
            candidate_name=interview.application.candidate_name if interview.application else "Candidate",
            candidate_email=interview.application.candidate_email if interview.application else "Email N/A",
            issue_type="technical",
            description="Terminated by candidate (Tab closed)",
            status="pending"
        )
        db.add(system_issue)
        
        # Transition state
        from app.services.state_machine import CandidateStateMachine, TransitionAction
        fsm = CandidateStateMachine(db)
        try:
            fsm.transition(interview.application, TransitionAction.REJECT, notes="Candidate abandoned the session.")
        except Exception:
            if interview.application:
                interview.application.status = "rejected"
        
        db.commit()
        
        # Generate final report for whatever was answered so far in background
        background_tasks.add_task(_finalize_interview_and_report, interview_id)
        
        return {"success": True, "message": "Interview abandoned. Report generation queued."}
    except Exception as e:
        db.rollback()
        logger.error(f"Error in abandon_interview: {e}")
        raise HTTPException(status_code=500, detail="Failed to record abandonment.")

@router.get("/{interview_id}", response_model=InterviewDetailResponse)
def get_interview(
    interview_id: int,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """Get interview details (HR/super_admin only; prevents IDOR for dashboard users)."""
    interview = (
        db.query(Interview)
        .options(joinedload(Interview.application))
        .filter(Interview.id == interview_id)
        .first()
    )

    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )

    validate_hr_ownership_for_interview(interview, current_user, resource_name="interview")
    return interview

@router.get("/{interview_id}/report", response_model=InterviewReportResponse)
async def get_interview_report(
    interview_id: int,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """Get interview report (HR only)"""
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    validate_hr_ownership_for_interview(interview, current_user, resource_name="interview")
    
    report = db.query(InterviewReport).filter(
        InterviewReport.interview_id == interview_id
    ).first()
    
    # Task: On-the-fly report generation fallback
    if not report and interview.status in ["completed", "terminated"]:
        logger.info(f"Report missing for finished interview {interview_id}. Generating on-the-fly.")
        report = await _finalize_interview_and_report_internal(db, interview_id)
        
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not yet available"
        )
    
    # Return report data plus video_url from interview — only when a recording actually exists
    report_dict = {column.name: getattr(report, column.name) for column in report.__table__.columns}
    
    if interview.video_recording_path:
        report_dict['video_url'] = f"/api/interviews/{interview.id}/video-stream"
    else:
        report_dict['video_url'] = None
    
    return report_dict

@router.get("/{interview_id}/video-stream")
async def get_video_stream(
    interview_id: int,
    request: Request,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """Return redirect to signed video URL from Supabase (HR only)"""
    _settings = __import__('app.core.config', fromlist=['get_settings']).get_settings()
    _get_signed_url = __import__('app.core.storage', fromlist=['get_signed_url']).get_signed_url
    
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
        
    validate_hr_ownership_for_interview(interview, current_user, resource_name="interview")
    
    video_path = interview.video_recording_path
    if not video_path:
        raise HTTPException(status_code=404, detail="No video recording found for this interview")

    signed_url = _get_signed_url(_settings.supabase_bucket_videos, video_path)
    
    if not signed_url:
        raise HTTPException(status_code=500, detail="Failed to generate playback URL")

    return RedirectResponse(url=signed_url)

@router.post("/{interview_id}/transcribe")
@limiter.limit("20/minute")
async def transcribe_interview_audio(
    request: Request,
    interview_id: int,
    file: UploadFile = File(...),
    interview_session: Interview = Depends(get_current_interview),
    db: Session = Depends(get_db)
):
    """
    Transcribe audio recorded during an interview.
    Replays identical JSON for the same X-Request-ID within TTL (Redis when REDIS_URL is set).
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # ── SIZE LIMIT ──
    # Limit transcription audio to 15MB (sufficient for 2-3 mins of high-quality opus)
    MAX_AUDIO_SIZE = 15 * 1024 * 1024
    if file.size and file.size > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file too large. Maximum size allowed is {MAX_AUDIO_SIZE // (1024 * 1024)}MB."
        )

    rid = (request.headers.get("X-Request-ID") or "").strip()
    if rid and settings.enable_request_id_idempotency:
        cache_key = f"idem:interviews.transcribe:{interview_id}:{rid}"
        cached = _idem_cache_get(cache_key)
        if cached is not None:
            log_json(
                logger,
                "transcribe_idempotent_replay",
                level="info",
                extra={"interview_id": interview_id, "request_id_prefix": rid[:12]},
            )
            return cached
    
    import os
    import tempfile
    import shutil
    import traceback
    from datetime import datetime

    # Secure temporary file handling
    suffix = os.path.splitext(file.filename)[1] if (file.filename and os.path.splitext(file.filename)[1]) else ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        tmp_path = temp_file.name
    
    if not settings.groq_keys:
        logger.error(f"Transcription failed: GROQ_API_KEY is not set in environment variables.")
        raise HTTPException(
            status_code=500, 
            detail="Transcription service unavailable: GROQ_API_KEY is missing on server. Please contact support."
        )

    try:
        with open(tmp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file.file.close()
        
        file_size = os.path.getsize(tmp_path)
        logger.info(f"Transcription requested for Interview {interview_id}. File: {file.filename}, Size: {file_size} bytes")

        if file_size < 100: # Too small to be valid audio
            out = {"text": ""}
        else:
            text = await transcribe_audio(tmp_path)
            out = {"text": text}
        if rid and settings.enable_request_id_idempotency:
            _idem_cache_set(f"idem:interviews.transcribe:{interview_id}:{rid}", out, ttl_seconds=90)
        return out
    except Exception as e:
        logger.error(f"Transcription failure for interview {interview_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to process voice audio: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/{interview_id}/upload-video")
async def upload_interview_video(
    request: Request,
    interview_id: int,
    file: UploadFile = File(...),
    interview_session: Interview = Depends(get_current_interview),
    db: Session = Depends(get_db)
):
    """
    Upload the recorded video for the interview session.
    Replays identical JSON for the same X-Request-ID within TTL (Redis when REDIS_URL is set).
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    rid = (request.headers.get("X-Request-ID") or "").strip()
    if rid and settings.enable_request_id_idempotency:
        vkey = f"idem:interviews.upload_video:{interview_id}:{rid}"
        cached = _idem_cache_get(vkey)
        if cached is not None:
            log_json(
                logger,
                "upload_video_idempotent_replay",
                level="info",
                extra={"interview_id": interview_id, "request_id_prefix": rid[:12]},
            )
            return cached

    # 6. Upload to Supabase
    from app.core.storage import upload_file
    from datetime import datetime
    timestamp = int(get_ist_now().timestamp())
    filename = f"interview_{interview_id}_{timestamp}.webm"
    storage_path = f"{interview_id}/{filename}"
    
    try:
        if file.size and file.size > 150 * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Video file exceeds 150MB limit.")
            
        content = await file.read()
        logger.info(f"Uploading video for interview {interview_id}: size={len(content)} bytes, type={file.content_type}")
        returned_path = upload_file(
            settings.supabase_bucket_videos, 
            storage_path, 
            content, 
            content_type=file.content_type or "video/webm"
        )
        
        # Save cloud path to DB
        interview_session.video_recording_path = returned_path
        db.add(interview_session)
        db.commit()

        out = {"success": True, "path": returned_path}
        if rid and settings.enable_request_id_idempotency:
            _idem_cache_set(f"idem:interviews.upload_video:{interview_id}:{rid}", out, ttl_seconds=90)
        return out
    except Exception as e:
        logger.error(f"Video cloud upload failure: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save video to cloud storage: {str(e)}")
    finally:
        file.file.close()


@router.post("/{interview_id}/monitoring-events", response_model=MonitoringEventResponse)
@limiter.limit("40/minute")
async def create_monitoring_event(
    request: Request,
    interview_id: int,
    event_data: MonitoringEventCreate,
    interview_session: Interview = Depends(get_current_interview_any_status),
    db: Session = Depends(get_db)
):
    """
    Candidate endpoint to submit a proctoring/monitoring event silently.
    If a base64 frame snapshot is provided, uploads it to Supabase cloud storage.
    """
    if interview_session.id != interview_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # ── SIZE LIMIT ──
    # Limit frame snapshots to 1MB (standard JPEG at 640x480 is usually <100KB)
    if event_data.frame_snapshot and len(event_data.frame_snapshot) > 1 * 1024 * 1024:
        logger.warning(f"Large monitoring frame rejected for interview {interview_id}: {len(event_data.frame_snapshot)} chars")
        event_data.frame_snapshot = None # Discard the image but keep the event metadata

    storage_path = None
    if event_data.frame_snapshot and event_data.frame_snapshot.startswith("data:image"):
        try:
            import base64
            from app.core.storage import upload_file
            
            # Extract header and base64 string
            header, encoded = event_data.frame_snapshot.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            
            timestamp = int(get_ist_now().timestamp())
            filename = f"monitoring_{interview_id}_{timestamp}_{event_data.event_type}.jpg"
            cloud_path = f"monitoring_frames/{interview_id}/{filename}"
            
            returned_path = upload_file(
                settings.supabase_bucket_videos,
                cloud_path,
                image_bytes,
                content_type="image/jpeg"
            )
            if returned_path:
                storage_path = returned_path
        except Exception as e:
            logger.error(f"Failed to upload monitoring frame: {e}")

    event_record = InterviewMonitoringEvent(
        interview_id=interview_id,
        event_type=event_data.event_type,
        confidence_score=event_data.confidence_score,
        frame_image_path=storage_path,
        video_reference=event_data.video_reference,
        timestamp=get_ist_now()
    )
    db.add(event_record)
    db.commit()
    db.refresh(event_record)

    from app.core.storage import get_signed_url
    url = None
    if storage_path:
        url = get_signed_url(settings.supabase_bucket_videos, storage_path)

    return MonitoringEventResponse(
        id=event_record.id,
        interview_id=event_record.interview_id,
        event_type=event_record.event_type,
        timestamp=event_record.timestamp,
        confidence_score=event_record.confidence_score,
        frame_image_path=event_record.frame_image_path,
        frame_image_url=url,
        video_reference=event_record.video_reference
    )


@router.get("/{interview_id}/monitoring-events", response_model=List[MonitoringEventResponse])
async def get_monitoring_events(
    interview_id: int,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """
    HR / Admin endpoint to retrieve all monitoring events for an interview session,
    including pre-signed image URLs for frame review.
    """
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
        
    validate_hr_ownership_for_interview(interview, current_user, resource_name="interview")

    events = db.query(InterviewMonitoringEvent).filter(
        InterviewMonitoringEvent.interview_id == interview_id
    ).order_by(InterviewMonitoringEvent.timestamp.asc()).all()

    from app.core.storage import get_signed_urls
    
    # Batch request signed URLs to prevent N+1 API calls
    image_paths = [ev.frame_image_path for ev in events if ev.frame_image_path]
    url_map = get_signed_urls(settings.supabase_bucket_videos, image_paths) if image_paths else {}
    
    results = []
    for ev in events:
        url = url_map.get(ev.frame_image_path) if ev.frame_image_path else None
            
        results.append(MonitoringEventResponse(
            id=ev.id,
            interview_id=ev.interview_id,
            event_type=ev.event_type,
            timestamp=ev.timestamp,
            confidence_score=ev.confidence_score,
            frame_image_path=ev.frame_image_path,
            frame_image_url=url,
            video_reference=ev.video_reference
        ))
        
    return results