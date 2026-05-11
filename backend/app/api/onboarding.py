from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, UploadFile, File
from sqlalchemy import or_, text
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from app.infrastructure.database import get_db
from app.domain.models import User, Application, GlobalSettings, Notification
from app.domain.schemas import ApplicationResponse, OfferResponseRequest
from app.core.auth import get_current_hr, get_current_admin
from app.services.offer_letter_service import generate_offer_letter_pdf, get_offer_letter_data
from app.services.email_service import send_offer_letter_email, send_simple_email, send_onboarding_reminder_email, send_joining_confirmation_email
from app.core.config import get_settings
from typing import List, Optional
import os
import uuid
import logging
import json
import random
import string
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from fastapi.responses import FileResponse, RedirectResponse
from io import BytesIO
from app.core.storage import upload_file, get_signed_url, get_public_url, get_supabase_client
from app.core.timezone import get_ist_now

import secrets
import time
from collections import defaultdict

import httpx
from jinja2 import Template
from app.services.offer_letter_service import get_offer_letter_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
settings = get_settings()

RATE_LIMIT_STORAGE = defaultdict(list)
MAX_REQUESTS_PER_MIN = 10

def rate_limit(ip: str):
    redis_client = None
    if settings.redis_url:
        try:
            from app.core.redis_store import get_redis_client
            redis_client = get_redis_client()
        except Exception:
            pass
    
    if redis_client:
        try:
            import redis
            redis_key = f"rate_limit:onboarding:{ip}"
            current_count = redis_client.get(redis_key)
            if current_count is None:
                redis_client.setex(redis_key, 60, 1)
                return
            count = int(current_count)
            if count >= MAX_REQUESTS_PER_MIN:
                raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
            redis_client.incr(redis_key)
            return
        except HTTPException:
            raise
        except Exception:
            pass
    
    now = time.time()
    RATE_LIMIT_STORAGE[ip] = [t for t in RATE_LIMIT_STORAGE[ip] if now - t < 60]
    if len(RATE_LIMIT_STORAGE[ip]) >= MAX_REQUESTS_PER_MIN:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    RATE_LIMIT_STORAGE[ip].append(now)

def generate_short_id():
    """Point 1: Secure URL-safe short IDs."""
    return secrets.token_urlsafe(8)

def log_audit(db: Session, action: str, resource_id: int, user_id: Optional[int], details: dict, ip: str = "unknown", is_critical: bool = False):
    """Helper to record audit logs without repeating logic."""
    from app.services.candidate_service import CandidateService
    CandidateService(db).create_audit_log(
        user_id=user_id,
        action=action,
        resource_type="Application",
        resource_id=resource_id,
        details=details,
        is_critical=is_critical
    )

async def get_application_by_short_id(db: Session, short_id: str, lock=False):
    """Secure lookup: short_id -> Application."""
    query = db.query(Application).filter(Application.offer_short_id == short_id)
    if lock:
        query = query.with_for_update()
    return query.first()

from app.services.state_machine import CandidateStateMachine, TransitionAction, CandidateState

def check_hr_permission(user: User, application: Application, db: Session):
    """
    Standardize HR permission guard. 
    Enforces that HR users can only access their own applications.
    """
    from app.core.ownership import validate_hr_ownership
    try:
        validate_hr_ownership(application, user, resource_name="application")
        return True
    except HTTPException:
        raise HTTPException(
            status_code=403, 
            detail="Access denied: You do not have permission to manage this candidate."
        )

async def generate_pdf_via_puppeteer(html_content: str, filename: str, bucket: str) -> str:
    """
    Calls the frontend Puppeteer service to generate a pixel-perfect PDF.
    Uploads the resulting binary to Supabase.
    """
    settings = get_settings()
    # Call the Next.js API route we created
    # Ensure we use the correct base path even if env var is slightly misconfigured
    frontend_url = os.environ.get("FRONTEND_BASE_URL") or settings.frontend_base_url
    if "/calrims" not in frontend_url and settings.env != "production":
        frontend_url = f"{frontend_url.rstrip('/')}/calrims"
        
    pdf_service_url = f"{frontend_url.rstrip('/')}/api/generate-pdf/"
    
    start_time = time.time()
    logger.info(f"Starting Puppeteer PDF generation request to {pdf_service_url} for {filename}...")
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.post(
                pdf_service_url,
                json={"html": html_content},
                timeout=60.0
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Puppeteer responded in {elapsed_time:.2f} seconds with status {response.status_code}")
            
            if response.status_code != 200:
                logger.error(
                    f"PDF_GENERATION_FAILED: Puppeteer service at {pdf_service_url} "
                    f"returned {response.status_code}. Response: {response.text[:200]}"
                )
                raise Exception(
                    f"PDF Generation service is currently unavailable. "
                    f"Status: {response.status_code}. Please verify FRONTEND_BASE_URL is correct."
                )
            
            pdf_bytes = response.content
            if len(pdf_bytes) < 1000: # Safety check: too small for a PDF
                 logger.error(f"Generated PDF too small ({len(pdf_bytes)} bytes). Content: {pdf_bytes.decode('utf-8', errors='ignore')[:500]}")
                 raise Exception("Generated PDF is invalid or too small. Check template.")

            storage_path = f"onboarding/{filename}"
            
            # Upload to Supabase
            upload_start = time.time()
            result_url = upload_file(bucket, storage_path, pdf_bytes, content_type="application/pdf")
            if not result_url:
                 raise Exception(f"Failed to upload PDF to Supabase bucket '{bucket}'. Check storage permissions.")
                 
            logger.info(f"Uploaded PDF to Supabase in {time.time() - upload_start:.2f} seconds. Path: {result_url}")
            return result_url
        except Exception as e:
            logger.error(f"PDF generation or upload failed: {str(e)}")
            raise e

@router.get("/applications/{application_id}/offer-preview")
async def get_hr_offer_preview(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """HR-only preview of the rendered offer letter HTML."""
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    check_hr_permission(current_user, application, db)
    
    settings_records = db.query(GlobalSettings).all()
    gs = {s.key: s.value for s in settings_records}
    
    template_str = application.offer_template_snapshot or gs.get("offer_letter_template", "")
    if not template_str:
         raise HTTPException(status_code=400, detail="No offer template found. Set one in Settings.")
    
    data = get_offer_letter_data(
        application.candidate_name,
        application.job.title if application.job else "N/A",
        (application.job.domain if application.job else "Engineering") or "Engineering",
        application.joining_date or datetime.now(),
        gs.get("company_name", "Our Company"),
        gs.get("company_logo_url", ""),
        gs.get("hr_email", ""),
        gs.get("hr_name", ""),
        gs.get("hr_phone", ""),
        gs.get("company_address", "")
    )
    
    template = Template(template_str)
    return {"html": template.render(**data)}

@router.get("/candidates", response_model=None)
def get_onboarding_candidates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Fetch candidates in onboarding pipeline."""
    from sqlalchemy.orm import joinedload
    from app.domain.models import Job
    
    query = db.query(Application).filter(
        Application.status.in_(["hired", "pending_approval", "offer_sent", "accepted", "onboarded"])
    ).order_by(Application.id.desc())
    
    # Apply visibility isolation
    if current_user.role.lower() in ["hr", "staff"]:
        # Join Job to filter by ownership
        query = query.join(Application.job)
        query = query.filter(or_(Job.hr_id == current_user.id, Application.hr_id == current_user.id))
    # Super Admin sees all.
    # Super Admin sees all.
    
    total = query.count()
    candidates = query.options(
        joinedload(Application.job),
        joinedload(Application.hr)
    ).all()
    
    # Populate Ownership Context (Architecture Rule 3)
    for c in candidates:
        c.assigned_hr_id = c.hr_id
        c.assigned_hr_name = c.hr.full_name if c.hr else "Unknown"
        c.is_owner = (c.hr_id == current_user.id)
        
    return {"items": candidates, "total": total}

@router.post("/applications/{application_id}/send-offer")
async def request_offer_approval(
    application_id: int,
    joining_date: str,
    background_tasks: BackgroundTasks, # Added background_tasks here
    auto_approve: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Stage offer for approval or release directly if auto_approve is True."""
    application = db.query(Application).filter(Application.id == application_id).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    check_hr_permission(current_user, application, db)
    
    # State Machine Hardening
    from app.services.state_machine import CandidateStateMachine, TransitionAction
    fsm = CandidateStateMachine(db)
    
    # Validation Layer
    if not application.candidate_email:
        raise HTTPException(status_code=400, detail="Candidate email is missing")

    try:
        if 'T' in joining_date:
            jdate = datetime.fromisoformat(joining_date.replace('Z', '+00:00'))
        else:
            # Handle YYYY-MM-DD
            jdate = datetime.strptime(joining_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.error(f"Date parsing error: {e}")
        raise HTTPException(status_code=400, detail="Invalid joining date format. Expected YYYY-MM-DD or ISO format.")

    settings_records = db.query(GlobalSettings).all()
    gs = {s.key: s.value for s in settings_records}
    
    # Initialize basic offer fields
    application.joining_date = jdate
    application.offer_template_snapshot = gs.get("offer_letter_template")
    application.offer_token = str(uuid.uuid4())
    application.offer_short_id = generate_short_id()
    application.offer_token_expiry = get_ist_now() + timedelta(days=7)
    application.offer_token_used = False

    if auto_approve:
        # Idempotency guard for frontend retries
        if application.status == "offer_sent" and application.offer_sent:
            logger.warning(f"Frontend retry detected for App {application_id}. Offer already sent.")
            return {"status": "success", "message": "Offer released directly to candidate."}
            
        # Direct release path
        try:
            fsm.transition(application, TransitionAction.SEND_OFFER, user_id=current_user.id)
            
            # Generate PDF via Puppeteer (Phase 7 implementation)
            filename = f"offer_{application.id}_{int(datetime.now().timestamp())}.pdf"
            
            data = get_offer_letter_data(
                candidate_name=application.candidate_name,
                job_role=application.job.title if application.job else "N/A",
                department=(application.job.domain if application.job else "Engineering") or "Engineering",
                joining_date=application.joining_date,
                company_name=gs.get("company_name", "Our Company"),
                logo_url=gs.get("company_logo_url", ""),
                hr_email=gs.get("hr_email", ""),
                hr_name=gs.get("hr_name", ""),
                hr_phone=gs.get("hr_phone", ""),
                company_address=gs.get("company_address", "")
            )
            
            from jinja2 import Template
            template_str = application.offer_template_snapshot or gs.get("offer_letter_template", "")
            if not template_str:
                raise Exception("No offer template found in settings.")
            template = Template(template_str)
            rendered_html = template.render(**data)
            
            final_path = await generate_pdf_via_puppeteer(rendered_html, filename, settings.supabase_bucket_offers)
            
            application.offer_pdf_path = final_path
            application.offer_sent = True
            application.offer_sent_date = get_ist_now()
            application.offer_approval_status = "approved"
            application.offer_approved_by = current_user.id
            application.offer_approved_at = get_ist_now()
            application.offer_email_status = "pending"
            
            db.add(application)
            db.commit() # Commit status change before background task
            logger.info(f"Offer released and status committed for App {application_id}")
            
            background_tasks.add_task(process_offer_email, application.id, application.offer_pdf_path, gs.get("company_name", "Our Company"))
            return {"status": "success", "message": "Offer letter sent successfully."}
            
        except Exception as e:
            import traceback
            logger.error(f"OFFER_RELEASE_CRITICAL_FAILURE: {str(e)}\n{traceback.format_exc()}")
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Offer letter could not be sent: {str(e)}")
    else:
        # Staging path
        try:
            fsm.transition(application, TransitionAction.SEND_FOR_APPROVAL, user_id=current_user.id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        application.status = "pending_approval"
        application.offer_approval_status = "pending"
        
        db.add(application)
        log_audit(db, "OFFER_STAGED", application.id, current_user.id, {"joining_date": joining_date}, is_critical=True)

        # Notify Super Admins
        super_admins = db.query(User).filter(User.role == "super_admin").all()
        for admin in super_admins:
            db.add(Notification(
                user_id=admin.id,
                notification_type="OFFER_PENDING",
                title="Offer Approval Required",
                message=f"HR {current_user.full_name} has requested approval for {application.candidate_name}'s offer letter.",
                related_application_id=application.id
            ))
        
        db.commit()
        return {"status": "success", "message": "Offer letter staged for approval"}

@router.post("/applications/{application_id}/approve-offer")
async def approve_offer_letter(
    application_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """HR/Admin approves the offer. Only the Job Owner or Super Admin allowed."""
    application = db.query(Application).filter(Application.id == application_id).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    check_hr_permission(current_user, application, db)
    
    # State Machine Hardening
    from app.services.state_machine import CandidateStateMachine, TransitionAction
    fsm = CandidateStateMachine(db)
    try:
        fsm.transition(application, TransitionAction.SEND_OFFER, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    settings_records = db.query(GlobalSettings).all()
    gs = {s.key: s.value for s in settings_records}
    
    # PDF Generation (Puppeteer + Supabase)
    try:
        filename = f"offer_{application.id}_{int(datetime.now().timestamp())}.pdf"
        
        data = get_offer_letter_data(
            candidate_name=application.candidate_name,
            job_role=application.job.title if application.job else "N/A",
            department=(application.job.domain if application.job else "Engineering") or "Engineering",
            joining_date=application.joining_date,
            company_name=gs.get("company_name", "Our Company"),
            logo_url=gs.get("company_logo_url", ""),
            hr_email=gs.get("hr_email", ""),
            hr_name=gs.get("hr_name", ""),
            hr_phone=gs.get("hr_phone", ""),
            company_address=gs.get("company_address", "")
        )
        
        template_str = application.offer_template_snapshot or gs.get("offer_letter_template", "")
        if not template_str:
            raise Exception("Offer template missing")
            
        from jinja2 import Template
        template = Template(template_str)
        rendered_html = template.render(**data)
        
        # Call Puppeteer (Phase 7 implementation)
        final_path = await generate_pdf_via_puppeteer(rendered_html, filename, settings.supabase_bucket_offers)
        
        application.offer_pdf_path = final_path
        logger.info(f"Offer PDF generated and uploaded to Supabase: {final_path}")
    except Exception as e:
        logger.error(f"Puppeteer transition failed: {e}")
        log_audit(db, "OFFER_PDF_FAILED", application.id, current_user.id, {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Document generation failure: {str(e)}")

    # Update Application State
    application.offer_sent = True
    application.offer_sent_date = get_ist_now()
    application.offer_approval_status = "approved"
    application.offer_approved_by = current_user.id
    application.offer_approved_at = get_ist_now()
    application.offer_email_status = "pending"
    
    db.add(application)
    
    # Notify HR
    if application.hr_id:
        db.add(Notification(
            user_id=application.hr_id,
            notification_type="OFFER_APPROVED",
            title="Offer Approved",
            message=f"Offer letter for {application.candidate_name} has been approved and moved to transit.",
            related_application_id=application.id
        ))

    db.commit()

    background_tasks.add_task(process_offer_email, application.id, application.offer_pdf_path, gs.get("company_name", "Our Company"))
    return {"status": "success", "message": "Offer letter approved and email scheduled."}

async def process_offer_email(application_id: int, storage_path: str, company_name: str):
    """Internal task with email-safe short links (Point 1)."""
    from app.infrastructure.database import SessionLocal
    db = SessionLocal()
    try:
        application = db.query(Application).filter(Application.id == application_id).with_for_update().first()
        if not application or application.offer_email_status == "sent": return

        final_storage_path = application.offer_pdf_path or storage_path
        # Generate signed URL for attachment processing (Cloud Storage aware)
        final_url = get_signed_url(settings.supabase_bucket_offers, final_storage_path)
        
        # Link Safety: Use offer_token (UUID) for better uniqueness
        base_url = settings.frontend_base_url 
        accept_link = f"{base_url}/offer/respond?token={application.offer_token}&intent=accept"
        reject_link = f"{base_url}/offer/respond?token={application.offer_token}&intent=reject"

        await send_offer_letter_email(
            to_email=application.candidate_email,
            candidate_name=application.candidate_name,
            company_name=company_name,
            offer_letter_url=final_url,
            accept_link=accept_link,
            reject_link=reject_link
        )
        
        application.offer_email_status = "sent"
        db.commit()
        log_audit(db, "OFFER_EMAIL_SENT", application.id, None, {"recipient": application.candidate_email})
        
    except Exception as e:
        logger.error(f"Email failed: {e}")
        application = db.query(Application).filter(Application.id == application_id).with_for_update().first()
        if application:
            application.offer_email_status = "failed"
            application.offer_email_retry_count += 1
            db.commit()
            log_audit(db, "OFFER_EMAIL_FAILED", application_id, None, {"error": str(e)})
    finally:
        db.close()

@router.get("/offer")
async def get_offer_preview(request: Request, token: str, db: Session = Depends(get_db)):
    """Public preview with UUID token support & rate limiting."""
    rate_limit(request.client.host if request.client else "unknown")
    application = db.query(Application).filter(Application.offer_token == token).first()
    if not application:
        raise HTTPException(status_code=404, detail="Offer not found")
    
    if application.offer_token_used:
        raise HTTPException(status_code=400, detail="Offer already responded to.")
    
    if application.offer_token_expiry:
        expiry = application.offer_token_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < get_ist_now():
            raise HTTPException(status_code=400, detail="Offer expired.")

    company_name_setting = db.query(GlobalSettings).filter(GlobalSettings.key == "company_name").first()
    return {
        "candidate_name": application.candidate_name,
        "job_title": application.job.title if application.job else "Unknown Role",
        "joining_date": application.joining_date.isoformat() if application.joining_date else None,
        "company_name": company_name_setting.value if company_name_setting and company_name_setting.value else "Our Company"
    }

def generate_employee_id(db: Session):
    """Utility to generate a unique employee ID (Task 8)."""
    while True:
        emp_id = 'EMP-' + ''.join(random.choices(string.digits, k=6))
        exists = db.query(Application).filter(Application.employee_id == emp_id).first()
        if not exists:
            return emp_id

@router.post("/applications/{application_id}/capture-photo")
async def capture_photo(
    application_id: int,
    background_tasks: BackgroundTasks,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Save captured webcam photo for onboarded candidate to Supabase (Task 7)."""
    application = db.query(Application).filter(Application.id == application_id).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    check_hr_permission(current_user, application, db)
    
    if application.status not in ["accepted", "onboarded"]:
        raise HTTPException(status_code=400, detail="Photo capture only allowed for candidates who have accepted the offer.")

    try:
        content = await photo.read()
        filename = f"photo_{application_id}_{int(time.time())}.jpg"
        storage_path = f"{application_id}/{filename}"
        
        upload_file(settings.supabase_bucket_id_photos, storage_path, content, content_type="image/jpeg")
            
        application.candidate_photo_path = storage_path
        
        from app.services.candidate_service import CandidateService
        CandidateService(db).create_audit_log(current_user.id, "PHOTO_CAPTURED", "Application", application_id, {"storage_path": storage_path})
        
        db.commit()
        
        # Fire off joining confirmation email in the background
        # Note: In production we'd generate a fresh signed URL right before sending or attach directly from storage
        # Here we get a signed URL that's valid for enough time to download/attach the image
        photo_signed_url = get_signed_url(settings.supabase_bucket_id_photos, storage_path)
        
        # We need HR and Super Admin emails
        hr_email = application.hr.email if application.hr else None
        super_admins = db.query(User).filter(User.role == "super_admin").all()
        admin_emails = [admin.email for admin in super_admins if admin.email]
        
        emails_to_notify = []
        if hr_email: emails_to_notify.append(hr_email)
        emails_to_notify.extend(admin_emails)
        
        # Remove duplicates
        emails_to_notify = list(set(emails_to_notify))
        
        for email_addr in emails_to_notify:
            background_tasks.add_task(
                send_joining_confirmation_email,
                to_email=email_addr,
                candidate_name=application.candidate_name,
                job_title=application.job.title if application.job else "N/A",
                candidate_photo_url=photo_signed_url
            )
            
    except Exception as e:
        db.rollback()
        logger.error(f"Cloud photo save failed: {e}")
        raise HTTPException(status_code=500, detail=f"Photo save failed: {str(e)}")
        
    return {"status": "success", "candidate_photo_path": application.candidate_photo_path}

@router.post("/cron/check-reminders")
def check_onboarding_reminders(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    (System/Admin) Check for candidates joining in exactly 7 days and send reminder.
    Task 1 Requirement.
    """
    today = get_ist_now().date()
    target_date = today + timedelta(days=7)
    
    start_of_target = datetime.combine(target_date, datetime.min.time())
    end_of_target = datetime.combine(target_date, datetime.max.time())

    # Find candidates who accepted offer and join in exactly 7 days
    candidates = db.query(Application).filter(
        Application.status.in_(["accepted"]),
        Application.joining_date >= start_of_target,
        Application.joining_date <= end_of_target,
        Application.reminder_sent_at == None
    ).all()
    
    reminders_sent = 0
    super_admins = db.query(User).filter(User.role == "super_admin").all()
    admin_emails = [admin.email for admin in super_admins if admin.email]

    for app in candidates:
        hr_email = app.hr.email if app.hr else None
        
        emails_to_notify = []
        if hr_email: emails_to_notify.append(hr_email)
        emails_to_notify.extend(admin_emails)
        emails_to_notify = list(set(emails_to_notify))

        joining_date_str = app.joining_date.strftime("%B %d, %Y")
        job_title = app.job.title if app.job else "N/A"

        for email_addr in emails_to_notify:
            background_tasks.add_task(
                send_onboarding_reminder_email,
                to_email=email_addr,
                candidate_name=app.candidate_name,
                joining_date=joining_date_str,
                job_title=job_title
            )

        app.reminder_sent_at = get_ist_now()
        reminders_sent += 1
        
    db.commit()
    return {"status": "success", "reminders_queued": reminders_sent}

@router.post("/applications/{application_id}/generate-id-card")
async def generate_id_card(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Generate ID Card PDF with photo and employee details (Task 8)."""
    application = db.query(Application).filter(Application.id == application_id).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    check_hr_permission(current_user, application, db)
        
    if not application.candidate_photo_path:
        raise HTTPException(status_code=400, detail="Cannot generate ID card without photo capture.")

    # 1. Generate unique Employee ID if not exists
    if not application.employee_id:
        application.employee_id = generate_employee_id(db)

    # 2. Premium PDF Generation with Puppeteer
    try:
        from jinja2 import Environment, FileSystemLoader
        templates_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "templates")
        env = Environment(loader=FileSystemLoader(templates_dir))
        template = env.get_template("id_card_template.html")
        
        gs = {s.key: s.value for s in db.query(GlobalSettings).all()}
        
        # Get Candidate Photo (signed URL)
        photo_url = get_signed_url(settings.supabase_bucket_id_photos, application.candidate_photo_path)
        
        data = {
            "company_name": gs.get("company_name") or settings.company_name,
            "logo_url": gs.get("company_logo_url", ""),
            "candidate_name": application.candidate_name,
            "employee_id": application.employee_id,
            "job_role": application.job.title if application.job else "N/A",
            "department": (application.job.domain if application.job else "Engineering") or "HR",
            "joining_date": application.joining_date.strftime('%d %b %Y') if application.joining_date else "N/A",
            "photo_url": photo_url
        }
        
        rendered_html = template.render(**data)
        
        filename = f"id_card_{application.employee_id}.pdf"
        cloud_path = await generate_pdf_via_puppeteer(rendered_html, filename, settings.supabase_bucket_id_cards)
        
        application.id_card_url = cloud_path
        
        from app.services.candidate_service import CandidateService
        CandidateService(db).create_audit_log(current_user.id, "ID_CARD_GENERATED", "Application", application_id, {"employee_id": application.employee_id})
        db.commit()
        
        return {"status": "success", "id_card_url": application.id_card_url, "employee_id": application.employee_id}
        
    except Exception as e:
        db.rollback()
        logger.error(f"ID Card Generation Error: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

@router.get("/applications/{application_id}/download-id-card")
def download_id_card(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Generate a Signed URL for the generated ID card PDF (Task 8)."""
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application or not application.id_card_url:
        raise HTTPException(status_code=404, detail="ID Card not found")
        
    signed_url = get_signed_url(settings.supabase_bucket_id_cards, application.id_card_url)
    if not signed_url:
        raise HTTPException(status_code=500, detail="Failed to generate download link")

    return {"status": "success", "url": signed_url}

@router.post("/respond")
async def respond_to_offer(request: Request, response_req: OfferResponseRequest, db: Session = Depends(get_db)):
    """Public response with Row Locking & Short ID support (Point 1, 2, 6)."""
    rate_limit(request.client.host if request.client else "unknown")
    
    # Use offer_token (UUID) lookup with ROW LOCKING
    application = db.query(Application).filter(Application.offer_token == response_req.token).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="Offer token not found")
    
    if application.offer_token_used:
         raise HTTPException(status_code=400, detail="Response already processed. Access locked.")
    
    now = get_ist_now()
    target_action = TransitionAction.ACCEPT_OFFER if response_req.response_type == "accept" else TransitionAction.REJECT
    
    from app.services.state_machine import CandidateStateMachine
    fsm = CandidateStateMachine(db)
    try:
        fsm.transition(application, target_action)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    application.offer_token_used = True
    application.offer_response_status = response_req.response_type
    application.offer_response_date = now
    application.offer_accepted_ip = client_ip
    application.offer_accepted_user_agent = user_agent
    
    # Combined transaction (Phase 8 Fix)
    log_audit(db, f"OFFER_{response_req.response_type.upper()}", application.id, None, {
        "ip": client_ip,
        "ua": user_agent
    }, ip=client_ip, is_critical=True)

    db.commit() # Atomic release of lock

    return {"status": "success"}

@router.post("/bulk/request-approval")
async def bulk_request_approval(
    application_ids: List[int],
    joining_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Bulk stage offers."""
    results = {"success": [], "failed": []}
    for app_id in application_ids:
        try:
            await request_offer_approval(app_id, joining_date, db, current_user)
            results["success"].append(app_id)
        except Exception as e:
            results["failed"].append({"id": app_id, "error": str(e)})
    return results

@router.post("/bulk/approve")
async def bulk_approve_offers(
    application_ids: List[int],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Bulk approve offers."""
    results = {"success": [], "failed": []}
    for app_id in application_ids:
        try:
            await approve_offer_letter(app_id, background_tasks, db, current_user)
            results["success"].append(app_id)
        except Exception as e:
            results["failed"].append({"id": app_id, "error": str(e)})
    return results

@router.get("/analytics/offers")
def get_offer_analytics(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Recomputed Analytics from Audit Logs (Point 4)."""
    from app.domain.models import AuditLog
    
    total_approved = db.query(AuditLog).filter(AuditLog.action == "OFFER_APPROVED").count()
    total_accepted = db.query(AuditLog).filter(AuditLog.action == "OFFER_ACCEPTED").count()
    total_rejected = db.query(AuditLog).filter(AuditLog.action == "OFFER_REJECTED").count()
    
    # Calculate response times from Audit Log flow
    sent_logs = db.query(AuditLog).filter(AuditLog.action == "OFFER_APPROVED").all()
    resp_logs = db.query(AuditLog).filter(AuditLog.action.in_(["OFFER_ACCEPTED", "OFFER_REJECTED"])).all()
    
    resp_map = {log.resource_id: log.created_at for log in resp_logs}
    time_diffs = []
    for s_log in sent_logs:
        if s_log.resource_id in resp_map:
            diff = (resp_map[s_log.resource_id] - s_log.created_at).total_seconds()
            time_diffs.append(diff)
            
    avg_hours = (sum(time_diffs) / len(time_diffs) / 3600) if time_diffs else 0

    return {
        "total_offers_approved": total_approved,
        "acceptance_rate": (total_accepted / total_approved * 100) if total_approved > 0 else 0,
        "rejection_rate": (total_rejected / total_approved * 100) if total_approved > 0 else 0,
        "avg_response_time_hours": avg_hours,
        "source": "audit_logs"
    }

@router.post("/applications/{application_id}/onboard")
def complete_onboarding(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_hr)
):
    """Mark candidate as onboarded manually with transition guard."""
    application = db.query(Application).filter(Application.id == application_id).with_for_update().first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    check_hr_permission(current_user, application, db)
        
    # Relaxed Guard: Onboarding allowed even if before joining date, with a log warning.
    if application.joining_date:
        today = get_ist_now().date()
        joining_date = application.joining_date.date()
        if joining_date > today:
            days_remaining = (joining_date - today).days
            logger.warning(f"Early Onboarding: App {application.id} onboarded {days_remaining} days before joining date.")


    from app.services.state_machine import CandidateStateMachine, TransitionAction
    fsm = CandidateStateMachine(db)
    try:
        fsm.transition(application, TransitionAction.SYSTEM_ONBOARD, user_id=current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    application.onboarded_at = get_ist_now()
    
    log_audit(db, "ONBOARDED_MANUAL", application.id, current_user.id, {"status": "success"}, is_critical=True)
    db.commit()
    return {"status": "success"}

@router.post("/cron/check-arrivals")
def check_candidate_arrivals(db: Session = Depends(get_db)):
    """
    (System/Admin) Auto-transition candidates to 'onboarded' if joining date is today.
    Task 2 Requirement.
    """
    from app.services.state_machine import CandidateState
    today = get_ist_now().date()
    
    # Range check for the whole day
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())

    # Find candidates who accepted offer and join today
    candidates = db.query(Application).filter(
        Application.status == "accepted",
        Application.joining_date >= start_of_day,
        Application.joining_date <= end_of_day
    ).all()
    
    onboarded_count = 0
    for app in candidates:
        app.status = "onboarded"
        app.onboarded_at = get_ist_now()
        
        log_audit(db, "SYSTEM_AUTO_ONBOARD", app.id, None, {"reason": "Joining date reached"}, is_critical=True)
        
        # Notify HR
        if app.hr_id:
             db.add(Notification(
                 user_id=app.hr_id,
                 notification_type="CANDIDATE_ARRIVED",
                 title="Candidate Joined",
                 message=f"{app.candidate_name} has joined today. Capture photo and generate ID card.",
                 related_application_id=app.id
             ))
        onboarded_count += 1
        
    db.commit()
    return {"status": "success", "onboarded_count": onboarded_count}