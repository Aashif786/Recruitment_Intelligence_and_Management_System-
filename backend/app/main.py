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
from app.services.interview_engine.websocket_gateway import router as websocket_router

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

from app.migrations import run_startup_migrations, validate_required_columns
if os.environ.get("WORKER_ID", "0") == "0":
    if os.environ.get("RIMS_STARTUP_MIGRATIONS_DONE", "0") != "1":
        os.environ["RIMS_STARTUP_MIGRATIONS_DONE"] = "1"
        # try:
        #     run_startup_migrations(engine)
        #     validate_required_columns(engine)
        # except RuntimeError as e:
        #     sys.exit(1)

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


def _decode_json_response_body(response: JSONResponse):
    """Starlette JSONResponse exposes serialized JSON as `body` (bytes), not `content`."""
    body = getattr(response, "body", None)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def _headers_without_content_length(response: JSONResponse):
    """Avoid reusing Content-Length/Content-Type from a wrapped response (would mismatch new body)."""
    out = {}
    for k, v in response.headers.items():
        lk = k.lower()
        if lk in ("content-length", "content-type"):
            continue
        out[k] = v
    return out


class StandardizedAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()
        async def standardized_handler(request: FastAPIRequest) -> Any:
            try:
                response = await original_handler(request)
                if isinstance(response, JSONResponse):
                    payload = _decode_json_response_body(response)
                    if isinstance(payload, dict) and "success" in payload:
                        return response
                    error_msg = None
                    if response.status_code >= 400:
                         # Try to extract a specific error message from the body
                         if isinstance(payload, dict):
                              error_msg = payload.get("error") or payload.get("detail") or "Error"
                         else:
                              error_msg = str(payload) or "Error"

                    return JSONResponse(
                        status_code=response.status_code,
                        content={
                            "success": response.status_code < 400,
                            "data": payload,
                            "error": error_msg
                        },
                        headers=_headers_without_content_length(response),
                    )
                if hasattr(response, "status_code"):
                    return response
                return {
                    "success": True,
                    "data": response,
                    "error": None
                }
            except HTTPException as exc:
                raise exc
            except Exception as exc:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"[GLOBAL ERROR] Handler crash in {request.url.path}: {str(exc)}\n{error_trace}")
                raise exc
        return standardized_handler

app = FastAPI(
    title="HR Recruitment System API",
    description="AI-powered automated recruitment platform",
    version="1.0.0",
    redirect_slashes=True
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


from app.core.middleware import PerformanceLoggingMiddleware
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
app.include_router(websocket_router)

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
