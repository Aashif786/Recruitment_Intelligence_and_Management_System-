from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Response, Request
from typing import List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from app.infrastructure.database import get_db
from app.domain.models import User
from app.domain.schemas import UserRegister, UserLogin, TokenResponse, UserResponse, UserVerifyOTP, ForgotPasswordRequest, ResetPasswordRequest
from app.core.auth import hash_password, verify_password, create_access_token, get_current_user, get_current_admin, pwd_context
from app.services.email_service import send_otp_email, send_password_reset_email
from app.core.config import get_settings
from app.domain.models import Application, Job, User
import secrets
import string
import logging
from sqlalchemy import or_
from app.core.timezone import get_ist_now, to_naive_ist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

from app.core.rate_limiter import limiter

@router.get("/debug/data-health")
def data_health(request: Request, db: Session = Depends(get_db)):
    """Phase 9: Enhanced Safety & Monitoring Debugging Endpoint - Admin only"""
    from app.core.auth import get_current_admin
    try:
        user = get_current_user(request, db)
        get_current_admin(user)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from sqlalchemy import func, or_
    from app.domain.models import Application, Job, User, Interview
    return {
        "counts": {
            "applications": db.query(func.count(Application.id)).scalar(),
            "jobs": db.query(func.count(Job.id)).scalar(),
            "users": db.query(func.count(User.id)).scalar(),
            "interviews": db.query(func.count(Interview.id)).scalar()
        },
        "monitoring": {
            "stuck_resume_parsing": db.query(func.count(Application.id)).filter(
                Application.resume_status == "parsing",
                Application.parsing_started_at < get_ist_now() - timedelta(hours=1)
            ).scalar(),
            "failed_resume_parsing": db.query(func.count(Application.id)).filter(
                Application.resume_status == "failed"
            ).scalar(),
        },
        "timestamp": get_ist_now().isoformat()
    }

@router.post("/register", response_model=UserResponse)
@limiter.limit("20/minute")
def register(request: Request, user_data: UserRegister, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Register a new HR user with pending approval."""
    try:
        from app.core.email_utils import validate_email_strict
        user_data.email = validate_email_strict(user_data.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        if existing_user.approval_status == "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An approved account already exists for this email."
            )
        if existing_user.approval_status == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This email has been rejected and cannot be registered again."
            )
        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An approval request for this email is already pending Super Admin review."
            )

        try:
            raw_otp = ''.join(secrets.choice(string.digits) for _ in range(6))
            existing_user.password_hash = hash_password(user_data.password)
            existing_user.full_name = user_data.full_name
            existing_user.role = "pending_hr"
            existing_user.is_active = False
            existing_user.is_verified = False
            existing_user.approval_status = "pending"
            existing_user.otp_code = hash_password(raw_otp)
            existing_user.otp_expiry = get_ist_now() + timedelta(minutes=30)
            db.commit()
            db.refresh(existing_user)
            background_tasks.add_task(send_otp_email, existing_user.email, raw_otp)
            return existing_user
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail="Registration update failed safely.")

    role = "pending_hr"
    raw_otp = ''.join(secrets.choice(string.digits) for _ in range(6))
    hashed_otp = hash_password(raw_otp)
    hashed_password = hash_password(user_data.password)

    new_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        full_name=user_data.full_name,
        role=role,
        is_active=False,
        is_verified=False,
        approval_status="pending",
        otp_code=hashed_otp,
        otp_expiry=get_ist_now() + timedelta(minutes=30)
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        background_tasks.add_task(send_otp_email, new_user.email, raw_otp)
        return new_user
    except Exception as e:
        db.rollback()
        logger.error(f"Registration failed for {user_data.email}: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Registration creation failed")

@router.post("/verify", response_model=dict)
@limiter.limit("20/minute")
def verify_otp(request: Request, verification_data: UserVerifyOTP, db: Session = Depends(get_db)):
    """Verify user account with OTP"""
    email = verification_data.email.lower()

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.approval_status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been rejected and is permanently blocked."
        )

    if user.is_verified:
        return {"message": "User is already verified"}

    if not user.otp_expiry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP has been generated. Please register again."
        )

    expiry_time = to_naive_ist(user.otp_expiry)
        
    if get_ist_now() > expiry_time:
        try:
            user.otp_code = None
            user.otp_expiry = None
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please register again to receive a new OTP."
        )

    if not user.otp_code or not pwd_context.verify(verification_data.otp, user.otp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code"
        )

    try:
        user.is_verified = True
        user.otp_code = None
        user.otp_expiry = None
        db.commit()
        return {"message": "Account successfully verified. It will require Super Admin approval before login."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Verification finalization failed safely.")

@router.post("/login")
@limiter.limit("30/minute")
def login(request: Request, response: Response, credentials: UserLogin, db: Session = Depends(get_db)):
    """Login and set secure JWT HttpOnly cookie"""
    credentials.email = credentials.email.lower().strip()
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user:
        logger.warning(f"Login failed: User {credentials.email} not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    logger.info(f"Login attempt: User={credentials.email}")
    if not verify_password(credentials.password, user.password_hash):
        logger.warning(f"Login failed: Password mismatch for user {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not verified. Please verify your email first."
        )

    if user.approval_status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been rejected and is permanently blocked."
        )
    
    if user.role == "pending_hr" or user.approval_status != "approved" or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending approval by the Super Admin."
        )

    access_token_expires = timedelta(minutes=settings.jwt_expiration_minutes)
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name
    }
    access_token = create_access_token(token_data, access_token_expires)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=settings.env == "production",
        max_age=settings.jwt_expiration_minutes * 60,
        expires=settings.jwt_expiration_minutes * 60
    )

    return {
        "message": "Login successful",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "approval_status": user.approval_status,
            "created_at": user.created_at
        }
    }

@router.get("/hr-requests", response_model=List[UserResponse])
@limiter.limit("20/minute")
def get_hr_requests(
    request: Request, 
    status: str = "pending", 
    current_admin: User = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """List HR users by status for Super Admin management"""
    query = db.query(User).filter(User.role != "super_admin")
    
    if status == "pending":
        query = query.filter(User.approval_status == "pending", User.is_verified == True)
    elif status == "approved":
        query = query.filter(User.approval_status == "approved", User.is_active == True)
    elif status == "rejected":
        query = query.filter(User.approval_status == "rejected")
    
    return query.order_by(User.created_at.desc()).all()


@router.delete("/remove/{user_id}", response_model=dict)
@limiter.limit("10/minute")
def remove_hr_user(
    request: Request, 
    user_id: int, 
    current_admin: User = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """Soft-delete (deactivate) an approved HR user account"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user.role == "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot remove a Super Admin")

    user.is_active = False
    # Reassign candidates (Phase 3 fix)
    _reassign_managed_resources(db, user.id, current_admin.id)
    
    db.commit()
    return {"message": f"User {user.email} has been deactivated and candidates reassigned."}

def _reassign_managed_resources(db: Session, old_hr_id: int, fallback_user_id: int):
    """
    Find another active HR/Admin and reassign all jobs and applications.
    If no other HR exists, fallback to the current admin.
    """
    # 1. Update Jobs handler
    db.query(Job).filter(Job.hr_id == old_hr_id).update({"hr_id": fallback_user_id})
    # 2. Update Applications handler (active ones)
    db.query(Application).filter(Application.hr_id == old_hr_id).update({"hr_id": fallback_user_id})
    # This ensures RLS ownership is transferred


@router.get("/pending-approvals", response_model=List[UserResponse])
@limiter.limit("20/minute")
def get_pending_approvals(request: Request, current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """List HR users waiting for Super Admin approval"""
    pending_users = db.query(User).filter(
        User.role == "pending_hr",
        User.approval_status == "pending",
        User.is_verified == True
    ).order_by(User.created_at.desc()).all()
    return pending_users


@router.post("/approve/{user_id}", response_model=UserResponse)
@limiter.limit("10/minute")
def approve_hr_user(request: Request, user_id: int, current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Approve a pending or rejected HR user account"""
    user = db.query(User).filter(User.id == user_id, User.role != "super_admin").first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HR user not found")
    
    if user.approval_status == "approved" and user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already approved and active")

    user.role = "hr"
    user.is_active = True
    user.approval_status = "approved"
    db.commit()
    db.refresh(user)
    return user


@router.post("/reject/{user_id}", response_model=dict)
@limiter.limit("10/minute")
def reject_hr_user(request: Request, user_id: int, current_admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Reject a pending or active HR user account"""
    user = db.query(User).filter(User.id == user_id, User.role != "super_admin").first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HR user not found")

    user.is_active = False
    user.otp_code = None
    user.otp_expiry = None
    user.approval_status = "rejected"
    
    # Reassign candidates (Phase 3 fix)
    _reassign_managed_resources(db, user.id, current_admin.id)
    
    db.commit()
    return {"message": f"User {user.email} has been rejected and candidates reassigned."}


@router.post("/logout")
def logout(response: Response):
    """Clear the authentication cookie"""
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
        secure=settings.env == "production"
    )
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return current_user

@router.put("/me", response_model=UserResponse)
def update_current_user_info(
    data: dict, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """Update current user profile info"""
    if "full_name" in data:
        current_user.full_name = data["full_name"]
    if "profile_image_url" in data:
        current_user.profile_image_url = data["profile_image_url"]
    
    try:
        db.commit()
        db.refresh(current_user)
        return current_user
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update profile")

@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(request: Request, data: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Generate a password reset OTP and send email"""
    user = db.query(User).filter(User.email == data.email.lower()).first()
    
    # We return success even if user doesn't exist to prevent email enumeration
    if not user:
        logger.info(f"Forgot password requested for non-existent email: {data.email}")
        return {"message": "If an account exists with this email, a reset OTP has been sent."}
    
    raw_otp = ''.join(secrets.choice(string.digits) for _ in range(6))
    user.otp_code = hash_password(raw_otp)
    user.otp_expiry = get_ist_now() + timedelta(minutes=30)
    
    try:
        db.commit()
        background_tasks.add_task(send_password_reset_email, user.email, raw_otp)
        return {"message": "If an account exists with this email, a reset OTP has been sent."}
    except Exception as e:
        db.rollback()
        logger.error(f"Forgot password failed for {user.email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process request")

@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset password using OTP"""
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user:
         raise HTTPException(status_code=404, detail="User not found")
    
    if not user.otp_code or not user.otp_expiry:
        raise HTTPException(status_code=400, detail="No reset request found")
        
    expiry_time = to_naive_ist(user.otp_expiry)
        
    if get_ist_now() > expiry_time:
        raise HTTPException(status_code=400, detail="Reset OTP has expired")
        
    if not pwd_context.verify(data.otp, user.otp_code):
        raise HTTPException(status_code=400, detail="Invalid OTP code")
        
    try:
        user.password_hash = hash_password(data.new_password)
        user.otp_code = None
        user.otp_expiry = None
        db.commit()
        return {"message": "Password has been successfully reset"}
    except Exception as e:
        db.rollback()
        logger.error(f"Reset password failed for {user.email}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset password")