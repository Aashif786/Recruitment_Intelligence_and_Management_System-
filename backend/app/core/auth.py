from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends, status, Request
from sqlalchemy.orm import Session
import logging
from app.core.config import get_settings
from app.domain.models import User
from app.infrastructure.database import get_db, set_db_identity
from app.core.timezone import get_ist_now

settings = get_settings()
logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
APPROVALID_INTERVIEW_STATUSES = {"not_started", "in_progress", "completed", "cancelled", "terminated", "expired"}
APPROVED_STAFF_ROLES = {"super_admin", "hr"}
PENDING_STAFF_ROLE = "pending_hr"

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash. Truncate to 72 bytes for bcrypt compatibility."""
    if not plain_password:
        return False
    # BCrypt has a 72-byte limit; passlib with newer bcrypt drivers may raise ValueError
    # if this is exceeded. Since bcrypt ignores bytes beyond 72, we truncate manually.
    return pwd_context.verify(plain_password[:72], hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = get_ist_now() + expires_delta
    else:
        expire = get_ist_now() + timedelta(minutes=settings.jwt_expiration_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def verify_token(token: str) -> dict:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            # Explicitly validate expiration.
            options={"verify_exp": True},
        )
        return payload
    except JWTError as e:
        # Avoid logging the full token (may contain sensitive material); log only a short preview.
        preview = token[:10] + "..." if token else "<empty>"
        logger.warning(f"JWT decode failed: {str(e)} token_preview={preview}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def ensure_user_has_roles(user: User, allowed_roles: Iterable[str]) -> User:
    allowed_roles = set(allowed_roles)
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Role-based access restriction.",
        )
    return user


def ensure_approved_staff(user: User, allowed_roles: Optional[Iterable[str]] = None) -> User:
    normalized_roles = set(allowed_roles or APPROVED_STAFF_ROLES)
    if user.role not in normalized_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Role-based access restriction.",
        )

    if user.approval_status != "approved" or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not approved for dashboard access.",
        )

    return user

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user"""
    token = request.cookies.get("access_token") or request.cookies.get("hr_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        payload = verify_token(token)
        sub = payload.get("sub")
        role = payload.get("role")
        
        if sub is None or role is None:
            logger.error(f"JWT Payload missing sub or role: {payload}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id = int(sub)
        logger.info(f"[Auth] Validating user_id={user_id} with role '{role}'")
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            logger.warning(f"[Auth] User {user_id} not found in database")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # ── Phase 2 Fix: Row Level Security Identity ──
        set_db_identity(db, user.id)

        if user.role != role:
            logger.warning(f"[Auth] Role mismatch for user {user_id}: token={role}, db={user.role}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token role no longer matches this account",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info(f"[Auth] User {user_id} authenticated successfully as '{user.role}'")

        if user.role in APPROVED_STAFF_ROLES:
            ensure_approved_staff(user)
        elif user.role == PENDING_STAFF_ROLE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is pending Super Admin approval.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        elif user.approval_status == "rejected" or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        import traceback
        logger.error(f"[Auth] CRITICAL: Unexpected error in get_current_user: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal auth error"
        )


def get_current_hr(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure an approved HR or Super Admin session."""
    return ensure_approved_staff(current_user, {"super_admin", "hr"})

def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure user is an approved Super Admin."""
    return ensure_approved_staff(current_user, {"super_admin"})

def get_current_candidate(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure user is a Candidate"""
    return ensure_user_has_roles(current_user, {"candidate"})

def get_current_interview(
    request: Request,
    db: Session = Depends(get_db)
):
    """Dependency to get current authenticated interview session"""
    from app.domain.models import Interview
    try:
        # Prefer Authorization header over cookie to avoid HR/dashboard `access_token`
        # overriding the interview token.
        auth_header = request.headers.get("Authorization")
        cookie_token = request.cookies.get("access_token")
        token = None
        auth_header_present = bool(auth_header and auth_header.startswith("Bearer "))
        if auth_header_present:
            token = auth_header.split(" ")[1]
        else:
            token = cookie_token
                
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid interview credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = verify_token(token)

        # Debug info to validate we decoded what the frontend is sending.
        logger.info(
            "Interview auth token source "
            f"authorization_header_present={auth_header_present} cookie_present={bool(cookie_token)}"
        )
        logger.info(
            "Interview JWT decoded "
            f"role={payload.get('role')} sub={payload.get('sub')} exp={payload.get('exp')}"
        )
        
        if payload.get("role") != "interview":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: interview JWT required",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        sub = payload.get("sub")
        if sub is None:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: interview JWT missing sub",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        interview_id = int(sub)
        
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        
        # Check basic existence and active status
        if not interview:
            logger.warning(f"Interview auth failed: Record {interview_id} not found.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview session not found. Please contact support.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if interview.status != "in_progress":
            logger.warning(f"Interview auth failed: interview {interview_id} is {interview.status}")
            detail = "This interview session is no longer active."
            if interview.status == "completed":
                detail = "This interview has already been completed."
            elif interview.status == "terminated":
                detail = "This interview has been terminated due to a proctoring violation."
                
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check for hard expiration timestamp
        if interview.expires_at:
            exp_at = interview.expires_at
            if exp_at < get_ist_now():
                if interview.status != "expired":
                    logger.warning(f"Interview auth failed: Session {interview_id} expired at {exp_at}. Marking as expired.")
                    try:
                        interview.status = "expired"
                        db.commit()
                        
                        # Lightweight audit log
                        from app.domain.models import AuditLog
                        import json
                        log = AuditLog(
                            action="INTERVIEW_EXPIRED",
                            resource_type="Interview",
                            resource_id=interview.id,
                            details=json.dumps({"application_id": interview.application_id, "expired_at_timestamp": exp_at.isoformat()})
                        )
                        db.add(log)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.warning(f"Failed to mark interview {interview_id} as expired: {e}")
                
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Your interview session has expired. Please contact HR to re-issue your access key.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        
        return interview
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: invalid interview ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Internal auth error in get_current_interview: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal auth error"
        )


def get_current_interview_any_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Candidate interview dependency that validates the interview session from the JWT,
    but allows access even after the interview is no longer in_progress.
    Useful for read-only endpoints like fetching final stage/report.
    """
    from app.domain.models import Interview
    try:
        # Prefer Authorization header over cookie to avoid HR/dashboard `access_token`
        # overriding the interview token.
        auth_header = request.headers.get("Authorization")
        cookie_token = request.cookies.get("access_token")
        token = None
        auth_header_present = bool(auth_header and auth_header.startswith("Bearer "))
        if auth_header_present:
            token = auth_header.split(" ")[1]
        else:
            token = cookie_token

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid interview credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = verify_token(token)

        logger.info(
            "Interview auth token source (any status) "
            f"authorization_header_present={auth_header_present} cookie_present={bool(cookie_token)}"
        )
        logger.info(
            "Interview JWT decoded (any status) "
            f"role={payload.get('role')} sub={payload.get('sub')} exp={payload.get('exp')}"
        )

        if payload.get("role") != "interview":
            logger.warning(
                "Interview auth failed (any status): role mismatch "
                f"role={payload.get('role')} sub={payload.get('sub')}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: interview JWT required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        sub = payload.get("sub")
        if sub is None:
            logger.warning(
                "Interview auth failed (any status): missing sub "
                f"role={payload.get('role')}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: interview JWT missing sub",
                headers={"WWW-Authenticate": "Bearer"},
            )

        interview_id = int(sub)
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        if not interview:
            logger.warning(
                "Interview auth failed (any status): interview not found "
                f"interview_id={interview_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview session not found.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Check for hard expiration timestamp even for "any status" (read-only)
        if interview.expires_at:
            exp_at = interview.expires_at
            if exp_at < get_ist_now() and interview.status not in ["completed", "terminated", "cancelled", "expired"]:
                # If completed/terminated/cancelled/expired, we allow viewing the report/thank you/violation page
                logger.warning(f"Interview auth failed (any status): Session {interview_id} expired at {exp_at}. Marking as expired.")
                try:
                    interview.status = "expired"
                    db.commit()
                except Exception as e:
                    db.rollback()
                
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Your interview link has expired.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        return interview
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: invalid interview ID in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Internal auth error in get_current_interview_any_status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal auth error",
        )