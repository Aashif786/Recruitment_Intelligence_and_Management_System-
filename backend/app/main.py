import os
import sys
from pathlib import Path

# ── Passlib / bcrypt compatibility patch ──────────────────────────────────────
import importlib
import bcrypt as _bcrypt_mod
if not hasattr(_bcrypt_mod, "__about__"):
    _bcrypt_mod.__about__ = type("_about", (), {"__version__": _bcrypt_mod.__version__})()

_ph = importlib.import_module("passlib.handlers.bcrypt")
_ph.detect_wrap_bug = lambda ident: False
try:
    _ph.bcrypt.set_backend("default")
except Exception:
    pass
# ──────────────────────────────────────────────────────────────────────────────

if os.getenv("BACKEND_START_MODE") not in ["script", "docker"]:
    print("Use start.ps1 to run the backend")
    sys.exit(1)

# ── Environment Version Guard ──────────────────────────────────────────────
try:
    import psycopg2
    import PIL.Image
except ImportError as e:
    if "psycopg2._psycopg" in str(e) or "_imaging" in str(e):
        print("\n" + "!"*80)
        print("CRITICAL: Python Version Mismatch Detected in Environment!")
        print(f"Error: {str(e)}")
        print("\nYour virtual environment contains packages compiled for a different Python version.")
        print("ACTION REQUIRED: Run '.\\start.ps1 repair' in the backend directory.")
        print("!"*80 + "\n")
        sys.exit(1)
# ──────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException, status, Request as FastAPIRequest
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from typing import Callable, Any
import json
import logging

from app.core.auth import hash_password
from app.core.config import get_settings
from app.infrastructure.database import Base, engine
from app.api import auth, jobs, applications, interviews, decisions, notifications, analytics, tickets, support, hr_tickets, ops_email, settings as hr_settings, onboarding, repository
from app.domain.models import (
    User, Job, Application, ResumeExtraction, 
    Interview, InterviewQuestion, InterviewAnswer,
    HiringDecision, Notification,
    ApplicationStage, AuditLog, InterviewReport
)


from app.core.logging_config import setup_logging
from app.core.observability import log_json

settings = get_settings()

if os.environ.get("RIMS_LOGGING_DONE", "0") != "1":
    # Enable file logging in the 'logs' directory
    from pathlib import Path
    logs_dir = Path(__file__).parent.parent / "logs"
    setup_logging(logs_dir, settings.debug)
    os.environ["RIMS_LOGGING_DONE"] = "1"
logger = logging.getLogger(__name__)

settings.validate_config()

Base.metadata.create_all(bind=engine)

# Migration safety: Ensure message_id exists in attachment_resumes
try:
    with engine.connect() as conn:
        from sqlalchemy import text
        from app.migrations import column_exists
        if not column_exists(conn, "attachment_resumes", "message_id"):
            if "postgresql" in str(engine.url):
                conn.execute(text("ALTER TABLE attachment_resumes ADD COLUMN IF NOT EXISTS message_id VARCHAR(255) UNIQUE"))
            else:
                conn.execute(text("ALTER TABLE attachment_resumes ADD COLUMN message_id VARCHAR(255) UNIQUE"))
            conn.commit()
except Exception as e:
    logger.warning(f"Database migration check failed (attachment_resumes.message_id): {e}")

from app.migrations import run_startup_migrations, validate_required_columns
if os.environ.get("WORKER_ID", "0") == "0":
    if os.environ.get("RIMS_STARTUP_MIGRATIONS_DONE", "0") != "1":
        os.environ["RIMS_STARTUP_MIGRATIONS_DONE"] = "1"
        try:
            run_startup_migrations(engine)
            validate_required_columns(engine)
        except RuntimeError as e:
            sys.exit(1)

from app.infrastructure.database import SessionLocal

def bootstrap_super_admin():
    if not settings.super_admin_email or not settings.super_admin_password:
        return
    try:
        with SessionLocal() as db:
            existing_admin = db.query(User).filter(User.role == "super_admin").first()
            if existing_admin:
                return
            existing_email_user = db.query(User).filter(User.email == settings.super_admin_email.lower()).first()
            if existing_email_user:
                existing_email_user.role = "super_admin"
                existing_email_user.is_verified = True
                existing_email_user.is_active = True
                existing_email_user.approval_status = "approved"
                db.commit()
                return
            super_admin = User(
                email=settings.super_admin_email.lower(),
                full_name=settings.super_admin_full_name.strip() or "Super Admin",
                password_hash=hash_password(settings.super_admin_password),
                role="super_admin",
                is_verified=True,
                is_active=True,
                approval_status="approved"
            )
            db.add(super_admin)
            db.commit()
    except Exception as e:
        logger.error(f"Super Admin bootstrap failed: {str(e)}")

bootstrap_super_admin()


from app.core.standardized_route import StandardizedAPIRoute

app = FastAPI(
    title="HR Recruitment System API",
    description="AI-powered automated recruitment platform",
    version="1.0.0",
    redirect_slashes=True,
    docs_url="/docs" if settings.env != "production" else None,
    redoc_url="/redoc" if settings.env != "production" else None,
    openapi_url="/openapi.json" if settings.env != "production" else None,
)
app.router.route_class = StandardizedAPIRoute



import time
app.state.start_time = time.time()

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.rate_limiter import limiter

def cors_aware_rate_limit_handler(request: FastAPIRequest, exc: RateLimitExceeded):
    response = _rate_limit_exceeded_handler(request, exc)
    origin = request.headers.get("origin")
    if not origin and settings.env == "development":
        origin = settings.frontend_base_url
    allowed_origins = settings.get_allowed_origins()
    if origin and (origin in allowed_origins or "*" in allowed_origins or settings.env == "development"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, cors_aware_rate_limit_handler)


from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="127.0.0.1")

from app.core.middleware import PerformanceLoggingMiddleware, SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(PerformanceLoggingMiddleware)

allowed_origins = list(set(settings.get_allowed_origins()))
if settings.env == "development":
    allowed_origins = list(set(allowed_origins + ["http://localhost:3000", "http://127.0.0.1:3000"]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["System"])
def health_check():
    uptime_seconds = round(time.time() - app.state.start_time, 2)
    db_status = "ok"
    try:
        from sqlalchemy import text
        from app.infrastructure.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_status = "error"
    
    redis_status = "not_configured"
    if settings.redis_url:
        try:
            from app.core.redis_store import get_redis_client
            redis_client = get_redis_client()
            if redis_client:
                redis_client.ping()
                redis_status = "ok"
            else:
                redis_status = "unavailable"
        except Exception:
            redis_status = "error"
    
    supabase_status = "not_configured"
    if settings.supabase_url:
        try:
            from app.core.storage import get_supabase_client
            client = get_supabase_client()
            if client:
                client.table("users").select("id").limit(1).execute()
                supabase_status = "ok"
            else:
                supabase_status = "unavailable"
        except Exception:
            supabase_status = "error"
    
    rate_limiter_status = "active" if getattr(app.state, "limiter", None) else "inactive"
    return {
        "status": "ok",
        "details": {
            "db": db_status,
            "redis": redis_status,
            "supabase": supabase_status,
            "uptime": uptime_seconds,
            "env": settings.env,
            "rate_limit": rate_limiter_status
        }
    }

@app.get("/", tags=["System"])
def root():
    return {
        "success": True,
        "data": {
            "message": "HR Recruitment System API",
            "version": "1.0.0",
            "docs": "/docs"
        },
        "error": None
    }

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(interviews.router)
app.include_router(decisions.router)
app.include_router(notifications.router)
app.include_router(tickets.router)
app.include_router(support.router)
app.include_router(hr_tickets.router)
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(ops_email.router)
app.include_router(hr_settings.router)
app.include_router(onboarding.router)
app.include_router(repository.router)


from app.linkedin_auth import router as linkedin_router
app.include_router(linkedin_router, prefix="/auth")


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: FastAPIRequest, exc: RequestValidationError):
    errs = exc.errors()
    response = JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": "Validation failed: " + "; ".join([f"{e['loc'][-1]}: {e['msg']}" for e in errs])
        }
    )
    origin = request.headers.get("origin")
    allowed_origins = settings.get_allowed_origins()
    if origin and (origin in allowed_origins or "*" in allowed_origins or settings.env == "development"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

@app.exception_handler(HTTPException)
async def http_exception_handler(request: FastAPIRequest, exc: HTTPException):
    response = JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": exc.detail
        }
    )
    origin = request.headers.get("origin")
    allowed_origins = settings.get_allowed_origins()
    if origin and (origin in allowed_origins or "*" in allowed_origins or settings.env == "development"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: FastAPIRequest, exc: SQLAlchemyError):
    logger.error(f"DATABASE ERROR: {str(exc)}")
    response = JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": "Database error occurred"
        }
    )
    origin = request.headers.get("origin")
    allowed_origins = settings.get_allowed_origins()
    if origin and (origin in allowed_origins or "*" in allowed_origins or settings.env == "development"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

@app.exception_handler(Exception)
async def general_exception_handler(request: FastAPIRequest, exc: Exception):
    import traceback
    error_trace = traceback.format_exc()
    error_msg = f"[GLOBAL EXCEPTION] Unhandled error: {str(exc)}\n{error_trace}"
    logger.error(error_msg)
    
    detail = str(exc) if settings.debug else "An unexpected internal server error occurred."
    response = JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": detail
        }
    )
    origin = request.headers.get("origin")
    allowed_origins = settings.get_allowed_origins()
    if origin and (origin in allowed_origins or "*" in allowed_origins or settings.env == "development"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


#
# Note:
# This module must NOT start a server itself.
# Entrypoint is enforced via `start.ps1` and `BACKEND_START_MODE=script`.


import asyncio
from app.services.email_ingestion_service import fetch_resume_attachments
from app.infrastructure.database import SessionLocal
import os

async def imap_polling_loop():
    while True:
        try:
            db = SessionLocal()
            
            # Fetch global settings from DB
            from app.domain.models import GlobalSettings
            settings_records = db.query(GlobalSettings).all()
            settings_dict = {s.key: s.value for s in settings_records}
            
            auto_sync_enabled = settings_dict.get("auto_sync_enabled", "false").lower() == "true"
            
            if auto_sync_enabled:
                # Fetch automatically using settings
                imap_email = settings_dict.get("imap_email") or settings.imap_email or ''
                imap_password = settings_dict.get("imap_password") or settings.imap_password or ''

                if imap_email and imap_password:
                    fetch_resume_attachments(db, imap_email, imap_password)
                else:
                    logger.info("IMAP auto-sync skipped: IMAP credentials are not configured.")

                from app.services.email_ingestion_service import run_batch_resume_processing
                await run_batch_resume_processing(db)
            
            db.close()
        except Exception as e:
            logger.error(f"IMAP Polling Error: {e}")
        
        # Sleep for 60 seconds (1 minute) to avoid getting blocked by Google IMAP limits.
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    # Start the continuous email ingestion loop
    asyncio.create_task(imap_polling_loop())
