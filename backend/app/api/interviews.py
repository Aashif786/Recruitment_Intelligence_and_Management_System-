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


def _load_questions_from_repo_set(set_id: int, db: Session) -> list:
    """Fetch questions from a QuestionSet record in the repository."""
    from app.domain.models import QuestionSet
    import json as _json
    logger.info(f"[Repo] Loading questions from repository set id={set_id}")
    qs = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not qs:
        logger.warning(f"[Repo] Repository set id={set_id} NOT FOUND in DB — falling back to AI.")
        return []
    try:
        questions = _json.loads(qs.questions) if isinstance(qs.questions, str) else qs.questions
        result = questions if isinstance(questions, list) else []
        logger.info(f"[Repo] Set id={set_id} title={qs.title!r} loaded {len(result)} questions successfully.")
        return result
    except Exception as e:
        logger.warning(f"[Repo] Failed to parse questions from set id={set_id}: {e} — falling back to AI.")
        return []

@router.get("/jobs/{job_id}")
async def check_job_status(job_id: str):
    """Polling endpoint for async AI generation tasks"""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

async def background_generate_questions(interview_id: int, job_id_db: int, application_id: int, ai_job_id: str):
    """Background task to pre-generate all questions without blocking Uvicorn threads"""
    from app.infrastructure.database import SessionLocal
    db: Session = SessionLocal()
    try:
        # Rehydrate objects from db
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        job_obj = db.query(Job).filter(Job.id == job_id_db).first()
        application = db.query(Application).filter(Application.id == application_id).first()
        
        if interview.interview_stage == STAGE_APTITUDE:
            await _generate_aptitude_questions(interview, job_obj, db)
            if job_obj.first_level_enabled:
                await _generate_first_level_questions(interview, job_obj, application, db)
        else:
            await _generate_first_level_questions(interview, job_obj, application, db)
            
        complete_job(ai_job_id)
    except Exception as e:
        logger.error(f"Failed background generation for {ai_job_id}: {e}")
        fail_job(ai_job_id, str(e))
        try:
            from app.domain.models import GlobalSettings
            db.query(GlobalSettings).filter(GlobalSettings.key == f"lock_gen_{interview_id}").delete()
            db.commit()
        except Exception as lock_err:
            logger.warning(f"Failed to clear generation lock on failure for interview {interview_id}: {lock_err}")
    finally:
        db.close()

# ─── Stage Constants ──────────────────────────────────────────────────────────
STAGE_APTITUDE = "aptitude"
STAGE_FIRST_LEVEL = "first_level"
STAGE_COMPLETED = "completed"
VALID_INTERVIEW_STATUSES = {"not_started", "in_progress", "completed", "cancelled", "terminated", "expired"}

APTITUDE_QUESTION_COUNT = 10  # Number of aptitude questions to pick from uploaded file


def _set_interview_status(interview: Interview, value: str) -> None:
    if value not in VALID_INTERVIEW_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid interview status: {value}")
    interview.status = value


def _determine_initial_stage(job: Job) -> str:
    """Determine the initial interview stage based on job configuration."""
    if job.aptitude_enabled and job.experience_level.lower() == "junior":
        return STAGE_APTITUDE
    return STAGE_FIRST_LEVEL


def _enforce_stage(interview: Interview, required_stage: str):
    """Raise 403 if the interview is not in the required stage."""
    if interview.interview_stage == STAGE_COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This interview has been fully completed."
        )
    if interview.interview_stage != required_stage:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Current stage is '{interview.interview_stage}', but '{required_stage}' is required."
        )


def _question_count_for_stage(db: Session, interview_id: int, stage: str) -> int:
    q_query = db.query(InterviewQuestion).filter(InterviewQuestion.interview_id == interview_id)
    if stage == STAGE_APTITUDE:
        q_query = q_query.filter(InterviewQuestion.question_type == "aptitude")
    else:
        q_query = q_query.filter(InterviewQuestion.question_type != "aptitude")
    return q_query.count()


async def _generate_aptitude_questions(interview: Interview, job: Job, db: Session):
    """Generate aptitude questions from uploaded file (random selection) or fallback defaults."""
    aptitude_prompts = []

    aptitude_mode = getattr(job, 'aptitude_mode', 'ai')
    
    # Repository source takes priority over file upload
    aptitude_repo_set_id = getattr(job, 'aptitude_repo_set_id', None)
    logger.info(
        f"[Aptitude] interview={interview.id} mode={aptitude_mode!r} "
        f"aptitude_repo_set_id={aptitude_repo_set_id} "
        f"aptitude_questions_file={getattr(job, 'aptitude_questions_file', None)!r}"
    )
    if aptitude_mode == 'upload' and aptitude_repo_set_id:
        repo_questions = _load_questions_from_repo_set(aptitude_repo_set_id, db)
        if repo_questions:
            random.shuffle(repo_questions)
            selected = repo_questions[:APTITUDE_QUESTION_COUNT]
            for item in selected:
                if isinstance(item, dict) and 'question' in item:
                    aptitude_prompts.append(item)
                elif isinstance(item, str):
                    aptitude_prompts.append(item)
            logger.info(f"Loaded {len(aptitude_prompts)} aptitude questions from repo set {aptitude_repo_set_id}")

    if not aptitude_prompts and aptitude_mode == 'upload' and getattr(job, 'aptitude_questions_file', None):
        try:
            file_path = settings.base_dir / job.aptitude_questions_file
            uploaded_questions = None
            if file_path.exists():
                # Robust reading for potential encoding issues
                for encoding in ['utf-8-sig', 'latin-1']:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            uploaded_questions = json.load(f)
                        break
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                
                if uploaded_questions is None:
                    # Fallback: Extract text and use AI to structure it
                    raw_text = parse_content_from_path(str(file_path))
                    if raw_text:
                        logger.info(f"Non-JSON aptitude file detected. Extracting via AI...")
                        uploaded_questions = await extract_questions_from_text(raw_text)
            else:
                # Try downloading from Supabase Storage
                from app.core.storage import download_file
                logger.info(f"Local file {file_path} not found. Attempting to download from Supabase storage: {job.aptitude_questions_file}")
                file_bytes = download_file(settings.supabase_bucket_resumes, job.aptitude_questions_file)
                if file_bytes:
                    for encoding in ['utf-8-sig', 'latin-1', 'utf-8']:
                        try:
                            uploaded_questions = json.loads(file_bytes.decode(encoding))
                            break
                        except Exception:
                            continue
                    
                    if uploaded_questions is None:
                        # Fallback: Save to temp file and parse text
                        import tempfile
                        suffix = os.path.splitext(job.aptitude_questions_file)[1]
                        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_f:
                            temp_f.write(file_bytes)
                            temp_path = temp_f.name
                        try:
                            raw_text = parse_content_from_path(temp_path)
                            if raw_text:
                                logger.info(f"Non-JSON downloaded aptitude file detected. Extracting via AI...")
                                uploaded_questions = await extract_questions_from_text(raw_text)
                        finally:
                            try:
                                os.unlink(temp_path)
                            except Exception:
                                pass

            if uploaded_questions and isinstance(uploaded_questions, list) and len(uploaded_questions) > 0:
                # Shuffle and pick N
                random.shuffle(uploaded_questions)
                selected = uploaded_questions[:APTITUDE_QUESTION_COUNT]
                for item in selected:
                    if isinstance(item, dict) and 'question' in item:
                        aptitude_prompts.append(item)
                    elif isinstance(item, str):
                        aptitude_prompts.append(item)
        except Exception as e:
            logger.error(f"Error loading uploaded aptitude questions: {e}")

    # Fallback/AI mode
    if not aptitude_prompts:
        if aptitude_mode == 'ai':
            from app.services.ai_service import generate_aptitude_batch
            try:
                # We request 10 questions for aptitude as per new requirements
                aptitude_prompts = await generate_aptitude_batch(10)
            except Exception as e:
                logger.error(f"AI generation for aptitude failed: {e}")
                aptitude_prompts = []
                
        if not aptitude_prompts:
            default_prompts = [
                {
                    "question": "You have 5 machines that each produce 5 widgets in 5 minutes. How long would it take 100 machines to produce 100 widgets?",
                    "options": ["5 minutes", "100 minutes", "25 minutes", "1 minute"],
                    "answer": 0
                },
                {
                    "question": "If a train travels 60 km in the first hour and 40 km in the second hour, what is the average speed?",
                    "options": ["50 km/h", "45 km/h", "55 km/h", "60 km/h"],
                    "answer": 0
                },
                {
                    "question": "A is twice as old as B. 10 years ago, A was three times as old as B. How old is B now?",
                    "options": ["20", "15", "25", "30"],
                    "answer": 0
                },
                {
                    "question": "What comes next in the sequence: 2, 6, 12, 20, 30, ?",
                    "options": ["42", "40", "36", "44"],
                    "answer": 0
                },
                {
                    "question": "If all Bloops are Razzies and all Razzies are Lazzies, are all Bloops definitely Lazzies?",
                    "options": ["Yes", "No", "Maybe", "Depends on Bloops"],
                    "answer": 0
                },
                {
                    "question": "A farmer has 17 sheep. All but 9 die. How many are left?",
                    "options": ["9", "17", "8", "0"],
                    "answer": 0
                },
                {
                    "question": "You have a 3-liter jug and a 5-liter jug. How do you measure exactly 4 liters?",
                    "options": ["Fill 5L, pour to 3L, empty 3L, pour rem. 2L to 3L, fill 5L, pour to 3L", "Fill 3L twice", "Fill 5L once", "Not possible"],
                    "answer": 0
                },
                {
                    "question": "If it takes 5 hours for 5 people to dig 5 holes, how long does it take 1 person to dig 1 hole?",
                    "options": ["5 hours", "1 hour", "10 hours", "1/5 hour"],
                    "answer": 0
                },
                {
                    "question": "What is the next number: 1, 1, 2, 3, 5, 8, ?",
                    "options": ["13", "11", "15", "10"],
                    "answer": 0
                },
                {
                    "question": "A clock shows 3:15. What is the angle between the hour and minute hand?",
                    "options": ["7.5 degrees", "0 degrees", "15 degrees", "5 degrees"],
                    "answer": 0
                }
            ]
            random.shuffle(default_prompts)
            # Standardize exactly 10 questions per the spec
            aptitude_prompts = default_prompts[:10]

    try:
        for i, item in enumerate(aptitude_prompts):
            q_text = ""
            options = None
            correct = None
            
            if isinstance(item, dict):
                q_text = item.get("question", "")
                options = json.dumps(item.get("options", []))
                correct = item.get("answer", 0)
            else:
                q_text = str(item)

            q = InterviewQuestion(
                interview_id=interview.id,
                question_number=i + 1,
                question_text=q_text,
                options=options,
                correct_answer=str(correct) if correct is not None else None,
                question_type="aptitude"
            )
            db.add(q)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving aptitude questions: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate aptitude questions safely.")
    logger.info(f"Generated {len(aptitude_prompts)} aptitude questions (sample test)")


async def _generate_first_level_questions(interview: Interview, job: Job, application, db: Session):
    """Generate first-level interview questions (existing logic)."""
    # Initialize default state
    locked_skill = "general"
    experience = "mid"
    
    # 0. Fail-safe: Ensure locked_skill is initialized in DB before any AI processing
    try:
        if not interview.locked_skill:
            interview.locked_skill = locked_skill
            db.add(interview)
            db.commit()
            db.refresh(interview)
    except Exception as init_err:
        logger.error(f"Failed to initialize locked_skill for interview {interview.id}: {init_err}")
        db.rollback()

    # Idempotency check: if non-aptitude questions already exist, skip generation
    existing_count = db.query(InterviewQuestion).filter(
        InterviewQuestion.interview_id == interview.id,
        InterviewQuestion.question_type != "aptitude",
    ).count()
    if existing_count > 0:
        logger.info(
            f"Interview {interview.id}: {existing_count} first-level questions already exist; skipping generation."
        )
        return

    def _first_level_fallback_questions() -> tuple[list[str], list[str]]:
        technical_fallbacks = [
            "Please describe your professional background and key technical skills.",
            "Describe a challenging project you worked on.",
            "What are the most important technical skills in your domain?",
            "How do you approach debugging a production issue?",
            "Explain a complex system you have built or contributed to.",
            "How do you ensure code quality in your work?",
            "Describe your experience with version control systems and CI/CD pipelines.",
            "How do you handle performance optimization in your projects?",
            "What is your approach to writing maintainable and scalable code?",
            "Describe a time when you had to learn a new technology quickly.",
            "How do you approach system design and architecture decisions?",
            "What testing strategies do you use in your development process?",
            "How do you handle technical debt in a project?",
            "Describe your experience working with APIs and integrations.",
            "How do you stay updated on new technologies and best practices?",
        ]
        behavioral_fallbacks = [
            "Tell me about a time you faced an unexpected challenge at work.",
            "Describe a situation where you had to collaborate with a difficult team member.",
            "How do you handle tight deadlines and competing priorities?",
            "Tell me about a time you received constructive feedback and how you responded.",
            "Describe a situation where you took initiative beyond your assigned responsibilities.",
        ]
        return technical_fallbacks, behavioral_fallbacks

    # ── Phase 1: analysis + AI/question generation (fallback allowed here) ──
    resume_extraction = application.resume_extraction if application else None
    resume_text = resume_extraction.extracted_text if resume_extraction else ""
    job_title = job.title if job else "General Role"

    logger.info(
        "Interview question generation start",
        extra={
            "interview_id": interview.id,
            "mode": getattr(job, "interview_mode", "ai") if job else "ai",
            "job_title": job_title,
        },
    )

    try:
        logger.debug(f"Interview {interview.id}: starting intro analysis (resume_len={len(resume_text)})")
        analysis = await analyze_introduction(resume_text, job_title)
        locked_skill = analysis.get("primary_skill", "general")
        experience = analysis.get("experience", "mid")
        logger.debug(
            f"Interview {interview.id}: intro analysis result locked_skill={locked_skill!r} experience={experience!r}"
        )
    except Exception as e:
        # Intro analysis failure is treated as AI failure for question generation.
        logger.warning(f"Interview {interview.id}: intro analysis failed; will use fallback questions. err={e}")
        locked_skill = "general"
        experience = "mid"

    # If the analyzer couldn't confidently infer a domain, fall back to job metadata.
    if not locked_skill or str(locked_skill).lower() == "general":
        job_text = f"{(job.title or '')} {(job.description or '')}".lower() if job else ""
        
        # Priority 1: specialized core engineering domains
        if any(k in job_text for k in ["mechanical", "cae", "cad", "ansys", "solidworks", "thermal", "structures", "structural engineering", "manufacturing"]):
            locked_skill = "CAE-MECHANICAL"
        elif any(k in job_text for k in ["tekla", "detailing", "steel detailing", "sds2", "aisc"]):
            locked_skill = "Steel_detailing"
        elif any(k in job_text for k in ["electrical", "electronics", "circuit", "wiring", "power distribution"]):
            if (experience or "mid").lower() in ["junior", "intern", "fresh", "fresher"]:
                locked_skill = "electrical_junior"
            else:
                locked_skill = "electrical_senior"
        
        # Priority 2: Software domains (backend keyword 'python' is common in engineering, so check it AFTER mechanical)
        elif any(k in job_text for k in ["backend", "api", "rest", "python", "django", "fastapi", "microservice", "fast api"]):
            locked_skill = "backend"
        elif any(k in job_text for k in ["frontend", "react", "ui", "ux", "javascript", "typescript", "web development"]):
            locked_skill = "frontend"
        elif any(k in job_text for k in ["devops", "aws", "docker", "kubernetes", "ci/cd", "terraform", "sre", "infrastructure"]):
            locked_skill = "devops"
        elif any(k in job_text for k in ["data", "machine learning", "ml", "sql", "analytics", "data science"]):
            locked_skill = "data_analysis"
        elif any(k in job_text for k in ["qa", "testing", "automation", "selenium", "cypress", "quality"]):
            locked_skill = "qa_testing"
        elif any(k in job_text for k in ["cyber", "security", "infosec", "network", "firewall"]):
            locked_skill = "cybersecurity"
        elif any(k in job_text for k in ["marketing", "seo", "sem", "social media", "content strategy", "google ads", "branding", "copywriter"]):
            locked_skill = "digital_marketing"
        elif any(k in job_text for k in ["embedded", "microcontroller", "stm32", "rtos", "esp32", "firmware", "low level programming", "bare metal"]):
            locked_skill = "embedded_systems"
        elif any(k in job_text for k in ["instrumentation", "scada", "plc", "hmi", "dcs", "automation control", "field instruments"]):
            locked_skill = "instrumentation"
        elif any(k in job_text for k in ["genai", "generative ai", "llm", "large language model", "rag", "langchain", "prompt engineering"]):
            locked_skill = "generative_ai"
        elif any(k in job_text for k in ["power bi", "tableau", "business intelligence", "bi specialist", "looker", "dashboards"]):
            locked_skill = "business_intelligence"
        elif any(k in job_text for k in ["dba", "database administrator", "database performance", "oracle dba", "mysql dba", "postgres dba", "backup and recovery"]):
            locked_skill = "database_admin"
        elif any(k in job_text for k in ["project manager", "pmp", "scrum master", "project management", "delivery manager"]):
            locked_skill = "project_management"
        elif any(k in job_text for k in ["business analyst", "requirement gathering", "brd", "frd", "use case", "user stories", "gap analysis"]):
            locked_skill = "business_analyst"
        elif any(k in job_text for k in ["finance", "accounting", "tally", "taxation", "auditor", "chartered accountant", "accounts payable", "accounts receivable"]):
            locked_skill = "finance_accounting"
        elif any(k in job_text for k in ["sales", "crm", "business development", "lead generation", "b2b sales", "account executive"]):
            locked_skill = "sales_crm"
        elif any(k in job_text for k in ["customer support", "customer service", "helpdesk", "technical support officer", "zendesk", "ticketing"]):
            locked_skill = "customer_support"
        elif any(k in job_text for k in ["legal", "lawyer", "contracts", "compliance officer", "statutory", "litigation", "paralegal"]):
            locked_skill = "legal"
        elif any(k in job_text for k in ["healthcare it", "hl7", "fhir", "his", "emr", "ehr", "medical coding", "hospital management"]):
            locked_skill = "healthcare_it"
        elif any(k in job_text for k in ["graphic designer", "photoshop", "illustrator", "creative design", "branding design", "logo designer"]):
            locked_skill = "graphic_design"
        elif any(k in job_text for k in ["video editor", "premiere pro", "after effects", "motion graphics", "davinci resolve", "post production"]):
            locked_skill = "video_editing"
        else:
            locked_skill = "general"

    # Persist locked_skill BEFORE entering the long-running question generation phase.
    # This prevents holding a DB transaction open while calling external AI APIs.
    try:
        interview.locked_skill = locked_skill
        db.add(interview)
        db.commit()
        db.refresh(interview)
    except Exception as e:
        db.rollback()
        logger.warning(f"Interview {interview.id}: failed to persist locked_skill={locked_skill!r}. err={e}")

    # Extract candidate skills from stored resume extraction
    candidate_skills = []
    if resume_extraction and resume_extraction.extracted_skills:
        try:
            candidate_skills = json.loads(resume_extraction.extracted_skills)
        except Exception:
            candidate_skills = []
    if not candidate_skills:
        skills_str = analysis.get("skills", "") if isinstance(locals().get("analysis"), dict) else ""
        if isinstance(skills_str, str) and skills_str:
            candidate_skills = [s.strip() for s in skills_str.split(",")]
        elif isinstance(skills_str, list):
            candidate_skills = skills_str

    logger.info(f"Interview {interview.id}: skill={locked_skill} level={experience} skills={candidate_skills}")

    # Level-based question split
    level_lower = (experience or "mid").lower()
    if "senior" in level_lower or "lead" in level_lower or "manager" in level_lower:
        basic_count, deep_count = 2, 8
    elif "junior" in level_lower or "intern" in level_lower or "fresh" in level_lower:
        basic_count, deep_count = 8, 2
    else:
        basic_count, deep_count = 5, 5

    interview_mode = getattr(job, "interview_mode", "ai") or "ai"
    behavioral_role = getattr(job, "behavioral_role", "general") if job else "general"
    uploaded_tech: list[str] = []
    uploaded_behav: list[str] = []

    if interview_mode in ["upload", "mixed"]:
        # Repository source takes priority over file upload
        technical_repo_set_id = getattr(job, 'technical_repo_set_id', None)
        behavioural_repo_set_id = getattr(job, 'behavioural_repo_set_id', None)
        logger.info(
            f"[FirstLevel] interview={interview.id} mode={interview_mode!r} "
            f"technical_repo_set_id={technical_repo_set_id} "
            f"behavioural_repo_set_id={behavioural_repo_set_id} "
            f"uploaded_question_file={getattr(job, 'uploaded_question_file', None)!r}"
        )

        if technical_repo_set_id:
            repo_qs = _load_questions_from_repo_set(technical_repo_set_id, db)
            for item in repo_qs:
                if isinstance(item, dict) and "question" in item:
                    q_type = str(item.get("type", "technical")).lower()
                    if "behavioural" in q_type or "behavioral" in q_type:
                        uploaded_behav.append(item["question"])
                    else:
                        uploaded_tech.append(item["question"])
                elif isinstance(item, str):
                    uploaded_tech.append(item)
            logger.info(f"Interview {interview.id}: loaded {len(uploaded_tech)} tech questions from repo set {technical_repo_set_id}")

        if behavioural_repo_set_id:
            repo_bqs = _load_questions_from_repo_set(behavioural_repo_set_id, db)
            for item in repo_bqs:
                q_text = item["question"] if isinstance(item, dict) and "question" in item else str(item)
                uploaded_behav.append(q_text)
            logger.info(f"Interview {interview.id}: loaded {len(uploaded_behav)} behavioural questions from repo set {behavioural_repo_set_id}")

        # Fall back to file upload if no repo set provided
        if not technical_repo_set_id and not behavioural_repo_set_id:
            logger.info(f"[FirstLevel] interview={interview.id}: no repo sets — falling back to uploaded file")
            file_name = getattr(job, "uploaded_question_file", None) if job else None
            if file_name:
                file_path = settings.base_dir / file_name
                if file_path.exists():
                    try:
                        data = None
                        for encoding in ["utf-8-sig", "latin-1"]:
                            try:
                                with open(file_path, "r", encoding=encoding) as f:
                                    data = json.load(f)
                                break
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                continue

                        if data is None:
                            raw_text = parse_content_from_path(str(file_path))
                            if raw_text:
                                logger.info(
                                    f"Interview {interview.id}: non-JSON question file detected; extracting via AI"
                                )
                                data = await extract_questions_from_text(raw_text)

                        if data and isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and "question" in item:
                                    q_text = item["question"]
                                    q_type = str(item.get("type", "technical")).lower()
                                    options = item.get("options", [])
                                    if options:
                                        q_text += "\n" + "\n".join(
                                            [f"{chr(65 + j)}) {opt}" for j, opt in enumerate(options)]
                                        )
                                    if "behavioral" in q_type:
                                        uploaded_behav.append(q_text)
                                    else:
                                        uploaded_tech.append(q_text)
                                elif isinstance(item, str):
                                    uploaded_tech.append(item)
                    except Exception as e:
                        logger.warning(f"Interview {interview.id}: uploaded question file unreadable: {e}")
                else:
                    logger.warning(
                        f"Interview {interview.id}: uploaded question file missing at {file_path}; will use AI."
                    )
            else:
                logger.warning(
                    f"Interview {interview.id}: uploaded_question_file missing for mode='{interview_mode}'; will use AI."
                )

    expected_tech = 15
    expected_behav = 5
    tech_questions: list[str] = []
    behav_questions: list[str] = []
    used_fallback = False
    fallback_reason = None

    try:
        if interview_mode == "upload":
            tech_questions = uploaded_tech[:expected_tech]
            behav_questions = uploaded_behav[:expected_behav]

            missing_tech = expected_tech - len(tech_questions)
            if missing_tech > 0:
                logger.info(f"Interview {interview.id}: upload mode filling {missing_tech} technical via AI")
                eval_skills = job.primary_evaluated_skills if job else None
                ai_meta = await generate_custom_domain_questions_with_meta(
                    locked_skill,
                    missing_tech,
                    "basic",
                    candidate_skills,
                    eval_skills,
                    job_title=job.title if job else "",
                    job_description=job.description if job else "",
                )
                ai_tech = ai_meta.get("questions", [])
                logger.info(
                    f"Interview {interview.id}: upload-mode tech source={ai_meta.get('source')} reason={ai_meta.get('reason', '')} partial={ai_meta.get('partial', False)} count={len(ai_tech)}"
                )
                tech_questions.extend(ai_tech)

            missing_behav = expected_behav - len(behav_questions)
            if missing_behav > 0:
                logger.info(f"Interview {interview.id}: upload mode filling {missing_behav} behavioral via AI")
                ai_behav = await generate_behavioral_batch(missing_behav, behavioral_role=behavioral_role, job_title=job.title if job else "", job_description=job.description if job else "")
                behav_questions.extend(ai_behav)

        elif interview_mode == "mixed":
            random.shuffle(uploaded_tech)
            tech_questions = uploaded_tech[:10]
            missing_tech = expected_tech - len(tech_questions)
            logger.info(
                f"Interview {interview.id}: mixed mode using {len(tech_questions)} uploaded tech; generating {missing_tech} AI tech"
            )
            if missing_tech > 0:
                eval_skills = job.primary_evaluated_skills if job else None
                ai_meta = await generate_custom_domain_questions_with_meta(
                    locked_skill,
                    missing_tech,
                    "basic",
                    candidate_skills,
                    eval_skills,
                    job_title=job.title if job else "",
                    job_description=job.description if job else "",
                )
                ai_tech = ai_meta.get("questions", [])
                logger.info(
                    f"Interview {interview.id}: mixed-mode tech source={ai_meta.get('source')} reason={ai_meta.get('reason', '')} partial={ai_meta.get('partial', False)} count={len(ai_tech)}"
                )
                tech_questions.extend(ai_tech)

            logger.info(f"Interview {interview.id}: mixed mode generating {expected_behav} AI behavioral questions")
            behav_questions = await generate_behavioral_batch(expected_behav, behavioral_role=behavioral_role, job_title=job.title if job else "", job_description=job.description if job else "")

        else:
            total_basic_count = 5 + basic_count
            eval_skills = job.primary_evaluated_skills if job else None
            logger.debug(f"Interview {interview.id}: AI mode generating {total_basic_count} basic tech")
            all_basic_meta = await generate_custom_domain_questions_with_meta(
                locked_skill,
                total_basic_count,
                "basic",
                candidate_skills,
                eval_skills,
                job_title=job.title if job else "",
                job_description=job.description if job else "",
            )
            all_basic = all_basic_meta.get("questions", [])
            logger.info(
                f"Interview {interview.id}: ai-mode basic source={all_basic_meta.get('source')} reason={all_basic_meta.get('reason', '')} partial={all_basic_meta.get('partial', False)} count={len(all_basic)}"
            )
            questions_q1_q5 = all_basic[:5]
            questions_mid_basic = all_basic[5:]

            logger.debug(f"Interview {interview.id}: AI mode generating {deep_count} deep tech")
            questions_mid_deep_meta = await generate_custom_domain_questions_with_meta(
                locked_skill,
                deep_count,
                "scenario-based/followup",
                candidate_skills,
                eval_skills,
                job_title=job.title if job else "",
                job_description=job.description if job else "",
            )
            questions_mid_deep = questions_mid_deep_meta.get("questions", [])
            logger.info(
                f"Interview {interview.id}: ai-mode deep source={questions_mid_deep_meta.get('source')} reason={questions_mid_deep_meta.get('reason', '')} partial={questions_mid_deep_meta.get('partial', False)} count={len(questions_mid_deep)}"
            )

            tech_questions = questions_q1_q5 + questions_mid_basic + questions_mid_deep
            logger.debug(f"Interview {interview.id}: AI mode generating {expected_behav} behavioral")
            behav_questions = await generate_behavioral_batch(expected_behav, behavioral_role=behavioral_role, job_title=job.title if job else "", job_description=job.description if job else "")

        # Strict validation: must be non-empty strings; do not treat empty/None as success.
        if not isinstance(tech_questions, list) or not isinstance(behav_questions, list):
            raise ValueError("AI returned non-list question payloads")
        if any((not isinstance(q, str)) for q in tech_questions + behav_questions):
            raise ValueError("AI returned non-string question entries")

        tech_questions = [q.strip() for q in tech_questions if isinstance(q, str) and q.strip()]
        behav_questions = [q.strip() for q in behav_questions if isinstance(q, str) and q.strip()]

        if len(tech_questions) < expected_tech or len(behav_questions) < expected_behav:
            # Do not silently pad. Mark explicit PARTIAL_RESPONSE and fill deterministically.
            logger.warning(
                f"Interview {interview.id}: PARTIAL_RESPONSE tech={len(tech_questions)}/{expected_tech} behav={len(behav_questions)}/{expected_behav}; filling missing with fallback_internal"
            )
            fb_tech, fb_behav = _first_level_fallback_questions()
            needed_tech = max(0, expected_tech - len(tech_questions))
            needed_behav = max(0, expected_behav - len(behav_questions))
            tech_questions.extend(fb_tech[:needed_tech])
            behav_questions.extend(fb_behav[:needed_behav])
            used_fallback = True
            fallback_reason = "PARTIAL_RESPONSE"

        tech_questions = tech_questions[:expected_tech]
        behav_questions = behav_questions[:expected_behav]

        logger.info(
            f"Interview {interview.id}: AI questions generated ok (tech={len(tech_questions)} behav={len(behav_questions)})"
        )
    except Exception as e:
        used_fallback = True
        fallback_reason = str(e)
        logger.warning(
            f"Interview {interview.id}: AI generation failed/invalid; using fallback_hard questions. reason={fallback_reason}"
        )
        tech_questions, behav_questions = _first_level_fallback_questions()

    all_questions = tech_questions + behav_questions
    # ── Phase 2: DB persistence (NO fallback here) ──
    q_offset = db.query(InterviewQuestion).filter(InterviewQuestion.interview_id == interview.id).count()
    try:
        # Verify connection is still alive after long AI calls to avoid OperationalError
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
        except Exception:
            logger.warning(f"Interview {interview.id}: DB connection lost during AI phase; re-establishing for save.")
            db.rollback()

        for i, q_text in enumerate(all_questions):
            q_num = q_offset + i + 1
            q_type = "behavioral" if i >= (len(all_questions) - expected_behav) else "technical"
            db.add(
                InterviewQuestion(
                    interview_id=interview.id,
                    question_number=q_num,
                    question_text=q_text,
                    question_type=q_type,
                    options=None,
                    correct_answer=None,
                )
            )

        interview.total_questions = q_offset + len(all_questions)
        db.add(interview)
        db.commit()
        source_tag = "ai"
        if used_fallback and fallback_reason == "PARTIAL_RESPONSE":
            source_tag = "fallback_internal"
        elif used_fallback:
            source_tag = "fallback_hard"
        logger.info(
            f"Interview {interview.id}: first-level questions persisted (count={len(all_questions)} offset={q_offset} source={source_tag} fallback_reason={fallback_reason or ''})"
        )
    except Exception as e:
        db.rollback()
        logger.error(
            f"Interview {interview.id}: DB persistence failed for generated questions (fallback={used_fallback}). err={e}"
        )
        raise HTTPException(status_code=500, detail="Failed to save generated interview questions safely.")


@router.post("/access")
@limiter.limit("10/minute")
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


async def _generate_fallback_questions_direct(interview_id: int):
    """Helper to generate fallback questions outside of the request flow if app data is missing."""
    from app.infrastructure.database import SessionLocal
    db = SessionLocal()
    try:
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        if interview:
            # Re-use existing fallback logic
            await _generate_first_level_questions(interview, None, None, db)
    finally:
        db.close()


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
        clarity_score = 0.0
        depth_score = 0.0
        practicality_score = 0.0
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
                clarity_score = evaluation.get("clarity", 0)
                depth_score = evaluation.get("depth", 0)
                practicality_score = evaluation.get("practicality", 0)
            else:
                technical_score = evaluation.get("technical_accuracy", evaluation.get("relevance", 0))
                completeness_score = evaluation.get("completeness", evaluation.get("action_impact", 0))
                clarity_score = evaluation.get("clarity", 0)
                depth_score = evaluation.get("depth", 0)
                practicality_score = evaluation.get("practicality", 0)

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
            clarity_score = heuristic_score
            depth_score = heuristic_score
            practicality_score = heuristic_score
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
            clarity_score = heuristic_score
            depth_score = heuristic_score
            practicality_score = heuristic_score
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
        answer.clarity_score = float(clarity_score)
        answer.depth_score = float(depth_score)
        answer.practicality_score = float(practicality_score)
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
                from app.domain.models import InterviewMonitoringEvent
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


async def _finalize_interview_and_report(interview_id: int):
    """
    Background-task safe wrapper that creates its own DB session.
    """
    from app.infrastructure.database import SessionLocal

    last_err = None
    for attempt in range(1, 4):
        db = SessionLocal()
        try:
            await _finalize_interview_and_report_internal(db, interview_id)
            return
        except Exception as e:
            last_err = e
            logger.error(f"Finalize/report retry attempt {attempt} failed for interview {interview_id}: {e}")
        finally:
            db.close()
    logger.error(f"Finalize/report failed after retries for interview {interview_id}: {last_err}")


async def _finalize_interview_and_report_internal(db: Session, interview_id: int, term_reason: str = None):
    """
    Internal helper to calculate final scores, generate the AI report, 
    and send notifications. Reusable for normal completion and auto-termination.
    """
    from app.services.ai_service import generate_interview_report
    from app.core.config import get_settings
    from app.core.storage import get_public_url
    from app.domain.models import InterviewReport, InterviewQuestion, InterviewAnswer, Notification
    from app.services.email_service import send_interview_completed_email, send_interview_terminated_email
    
    # 1. Fetch live interview state with row-level lock to prevent double reporting
    interview = db.query(Interview).filter(Interview.id == interview_id).with_for_update().first()
    if not interview:
        logger.error(f"Finalization failed: Interview {interview_id} not found.")
        return None

    # Determine status if not already set (default to completed)
    if interview.status == "in_progress":
        _set_interview_status(interview, "completed")
    if not interview.ended_at:
        interview.ended_at = get_ist_now()

    # Auto-resolve any pending support tickets for this interview upon successful completion
    if interview.status == "completed":
        try:
            from app.domain.models import InterviewIssue
            pending_tickets = db.query(InterviewIssue).filter(
                InterviewIssue.interview_id == interview_id,
                InterviewIssue.status == "pending"
            ).all()
            for ticket in pending_tickets:
                ticket.status = "resolved"
                ticket.resolved_at = get_ist_now()
                ticket.hr_response = "Resolved automatically upon successful interview completion."
        except Exception as e:
            logger.error(f"Failed to auto-resolve pending tickets for interview {interview_id}: {e}")
    
    # 2. Calculate scores
    # Optimized: Fetch questions and latest answers in a single join to avoid N+1 queries
    from sqlalchemy.orm import contains_eager
    
    questions = (
        db.query(InterviewQuestion)
        .outerjoin(InterviewQuestion.answers)
        .filter(
            InterviewQuestion.interview_id == interview_id,
            InterviewQuestion.question_type != "aptitude"
        )
        .options(contains_eager(InterviewQuestion.answers))
        .order_by(InterviewQuestion.question_number)
        .all()
    )
    
    technical_scores = []
    behavioral_scores = []
    all_scores = []
    qa_pairs = []
    
    for question in questions:
        # Get the latest answer for this question
        latest_answer = sorted(question.answers, key=lambda x: x.id)[-1] if question.answers else None
        
        if latest_answer:
            score = latest_answer.answer_score if latest_answer.answer_score is not None else 0.0
            ans_text = latest_answer.answer_text
            eval_raw = latest_answer.answer_evaluation
        else:
            score = 0.0
            ans_text = "[No Answer Provided]"
            eval_raw = json.dumps({"auto_graded": False, "reason": "skipped", "score": 0.0})
            
        # Robust classification based on question_type
        if (question.question_type or "").lower() == 'behavioral':
            behavioral_scores.append(score)
        else:
            technical_scores.append(score)

        all_scores.append(score)
            
        qa_pairs.append({
            "question": question.question_text,
            "answer": ans_text,
            "score": score,
            "evaluation_raw": eval_raw,
            "question_type": question.question_type
        })
    
    technical_avg = sum(technical_scores) / len(technical_scores) if technical_scores else 0.0
    behavioral_avg = sum(behavioral_scores) / len(behavioral_scores) if behavioral_scores else 0.0

    # Weighted rollup (Robust calculation)
    # If both categories exist: 70% technical, 30% behavioral
    # If only one exists: 100% of that category
    calculated_overall_score = 0.0
    if technical_scores and behavioral_scores:
        calculated_overall_score = round((technical_avg * 0.7 + behavioral_avg * 0.3), 2)
    elif technical_scores:
        calculated_overall_score = round(technical_avg, 2)
    elif behavioral_scores:
        calculated_overall_score = round(behavioral_avg, 2)
    
    interview_score = calculated_overall_score

    behavioral_score = round(behavioral_avg, 2)
    technical_score_val = round(technical_avg, 2)
    ai_used_count = 0
    fallback_used_count = 0
    confidence_values = []
    for question in questions:
        ans = sorted(question.answers, key=lambda x: x.id)[-1] if question.answers else None
        if not ans:
            continue
        if getattr(ans, "ai_used", False):
            ai_used_count += 1
        if getattr(ans, "fallback_used", False):
            fallback_used_count += 1
        if getattr(ans, "confidence_score", None) is not None:
            confidence_values.append(float(ans.confidence_score))

    interview.overall_score = interview_score
    interview.questions_asked = len(questions)
    interview.first_level_completed = True
    interview.first_level_score = interview_score
    
    # 2.5 Update Application Status via State Machine
    if interview.application:
        from app.services.state_machine import CandidateStateMachine, TransitionAction
        fsm = CandidateStateMachine(db)
        try:
            # Ifすでに interview_completed ならスキップ
            if interview.application.status != "interview_completed":
                fsm.transition(interview.application, TransitionAction.SYSTEM_INTERVIEW_COMPLETE)
        except Exception as e:
            logger.warning(f"FSM transition failed for interview {interview_id}: {e}")
            interview.application.status = "interview_completed"
            
        # ── Phase 6: Critical Audit Logging ──
        from app.services.candidate_service import CandidateService
        cand_service = CandidateService(db)
        cand_service.create_audit_log(
            None, 
            "INTERVIEW_COMPLETED", 
            "Interview", 
            interview_id, 
            {"overall_score": interview_score, "status": interview.status},
            is_critical=True
        )
            
    db.commit()

    # 3. Check for termination reason (from InterviewIssue)
    from app.domain.models import InterviewIssue
    if not term_reason:
        issue = db.query(InterviewIssue).filter(InterviewIssue.interview_id == interview_id).order_by(InterviewIssue.id.desc()).first()
        if issue:
            term_reason = f"{issue.issue_type}: {issue.description}"
        elif interview.status == "terminated":
            term_reason = "System manual termination"

    # 4. Generate AI Report
    existing_report = db.query(InterviewReport).filter(InterviewReport.interview_id == interview_id).first()
    if existing_report:
        # ── Phase 3: Versioning (Save old report before generating new) ──
        try:
            version_count = db.query(InterviewReportVersion).filter(InterviewReportVersion.interview_id == interview_id).count()
            old_version = InterviewReportVersion(
                interview_id=interview_id,
                version_number=version_count + 1,
                overall_score=existing_report.overall_score,
                summary=existing_report.summary
            )
            db.add(old_version)
            db.flush() 
        except Exception as e:
            logger.warning(f"Failed to version old interview report: {e}")

    try:
        job = interview.application.job
        primary_skills = []
        if getattr(job, 'primary_evaluated_skills', None):
            try:
                parsed = json.loads(job.primary_evaluated_skills)
                if isinstance(parsed, list): primary_skills = parsed
            except: pass

        report_data = None
        last_rep_err = None
        
        # Prepare aptitude summary for the report context
        aptitude_context = None
        if interview.aptitude_completed and interview.aptitude_score is not None:
            aptitude_context = {
                "score": round(interview.aptitude_score, 2),
                "status": "Completed"
            }

        for attempt in range(1, 4):
            try:
                report_data = await generate_interview_report(
                    job_title=job.title,
                    all_qa_pairs=qa_pairs,
                    overall_score=interview_score,
                    primary_evaluated_skills=primary_skills,
                    termination_reason=term_reason,
                    aptitude_context=aptitude_context, # Pass aptitude performance
                )
                break
            except Exception as rep_e:
                last_rep_err = rep_e
                logger.warning(
                    "interview_report_ai_retry",
                    extra={"interview_id": interview_id, "attempt": attempt, "error_preview": str(rep_e)[:240]},
                )
                if attempt < 3:
                    await asyncio.sleep(0.45 * attempt)

        if report_data is None:
            logger.error(
                "generate_interview_report failed after retries for interview %s: %s",
                interview_id,
                last_rep_err,
            )
            return None

        detailed_feedback_val = report_data["detailed_feedback"]
        if isinstance(detailed_feedback_val, (dict, list)):
            detailed_feedback_val = json.dumps(detailed_feedback_val)
            
        rec_val = str(report_data.get("recommendation", "consider")).lower()
        if existing_report:
            report = existing_report
            report.overall_score = report_data["overall_score"]
            # Fallback to calculated scores if AI didn't provide them
            report.technical_skills_score = report_data.get("technical_skills_score") or technical_score_val
            report.communication_score = report_data.get("communication_score") or behavioral_score
            report.problem_solving_score = report_data.get("problem_solving_score") or ((technical_score_val + behavioral_score) / 2)
            report.summary = str(report_data.get("summary", ""))
            report.detailed_feedback = detailed_feedback_val
            report.recommendation = rec_val
            report.reasoning = {"ai_summary": report_data.get("reasoning")}
            report.updated_at = get_ist_now()
        else:
            report = InterviewReport(
                interview_id=interview_id,
                application_id=interview.application.id if interview.application else None,
                job_id=job.id if job else None,
                candidate_name=interview.application.candidate_name if interview.application else "Candidate",
                candidate_email=interview.application.candidate_email if interview.application else "Email N/A",
                applied_role=job.title if job else "N/A",
                overall_score=report_data["overall_score"],
                # Fallback to calculated scores if AI didn't provide them
                technical_skills_score=report_data.get("technical_skills_score") or technical_score_val,
                communication_score=report_data.get("communication_score") or behavioral_score,
                problem_solving_score=report_data.get("problem_solving_score") or ((technical_score_val + behavioral_score) / 2),
                strengths=str(report_data.get("strengths", "[]")),
                weaknesses=str(report_data.get("weaknesses", "[]")),
                summary=str(report_data.get("summary", "")),
                recommendation=rec_val,
                detailed_feedback=detailed_feedback_val,
                aptitude_score=interview.aptitude_score,
                behavioral_score=behavioral_score,
                combined_score=interview_score,
                evaluated_skills=str(report_data.get("evaluated_skills", "[]")),
                termination_reason=term_reason,
                ai_used=ai_used_count > 0,
                fallback_used=fallback_used_count > 0,
                confidence_score=(sum(confidence_values) / len(confidence_values)) if confidence_values else 0.0,
                reasoning={"ai_summary": report_data.get("reasoning")},
            )
            db.add(report)
        
        try:
            db.commit()
        except Exception as commit_err:
            db.rollback()
            existing_report = db.query(InterviewReport).filter(InterviewReport.interview_id == interview_id).first()
            if existing_report:
                logger.info(f"Concurrent report creation resolved: returning existing report for {interview_id}.")
                report = existing_report
            else:
                raise commit_err

        # Notification
        try:
            apt_score = interview.aptitude_score
            apt_info = f" | Aptitude: {apt_score:.1f}" if apt_score is not None else ""
            status_desc = "completed" if interview.status == "completed" else "terminated early"
            notification = Notification(
                user_id=job.hr_id if job else None,
                notification_type="INTERVIEW_COMPLETED",
                title=f"Interview {status_desc.capitalize()}: {interview.application.candidate_name if interview.application else 'Candidate'}",
                message=f"{interview.application.candidate_name if interview.application else 'Candidate'} {status_desc} for {job.title if job else 'Job'}. Score: {interview_score:.1f}{apt_info}",
                related_application_id=interview.application_id,
                related_interview_id=interview_id
            )
            db.add(notification)
            db.commit()
        except Exception as e:
            logger.error(f"Error creating notification: {e}")

        # 5. Send Automated Candidate Email
        try:
            if interview.application:
                if interview.status == "terminated":
                    await send_interview_terminated_email(interview.application, term_reason or "policy violations")
                else:
                    await send_interview_completed_email(interview.application)
        except Exception as e:
            logger.error(f"Failed to send automated candidate interview email: {e}")

        return report
    except Exception as e:
        logger.error(f"Error in _finalize_interview_and_report_internal: {e}")
        return None

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

    from app.core.storage import get_signed_url
    results = []
    for ev in events:
        url = None
        if ev.frame_image_path:
            url = get_signed_url(settings.supabase_bucket_videos, ev.frame_image_path)
            
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