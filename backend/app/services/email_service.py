import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import asyncio
import base64
from app.core.config import get_settings
import logging
from urllib.parse import urlparse, urlencode
import httpx
import traceback
import uuid
from datetime import datetime
from typing import Any, Optional

settings = get_settings()
logger = logging.getLogger(__name__)

def _safe_email_target(to_email: str) -> str:
    """PII-safe target string for logs/audits."""
    try:
        from app.core.observability import safe_hash
        return safe_hash((to_email or "").lower().strip())
    except Exception:
        return "<hash_error>"

def _audit_email_event(action: str, *, to_email: str, details: dict[str, Any]) -> None:
    """
    Best-effort DB audit log for email events.
    Never raises (email failures must not crash request flow).
    """
    try:
        from app.infrastructure.database import SessionLocal
        from app.domain.models import AuditLog
        import json

        payload = {
            "to_hash": _safe_email_target(to_email),
            **(details or {}),
        }
        with SessionLocal() as db:
            db.add(
                AuditLog(
                    user_id=None,
                    action=action,
                    resource_type="Email",
                    resource_id=None,
                    details=json.dumps(payload),
                    ip_address=None,
                )
            )
            db.commit()
    except Exception:
        # Intentionally silent: DB may be down and should not affect email flow.
        pass

def _is_gmail_quota_error(error: BaseException | str) -> bool:
    msg = str(error or "")
    return ("Daily user sending limit exceeded" in msg) or ("5.4.5" in msg and "sending limit" in msg)

def _send_via_smtp(to_email: str, subject: str, html_body: str, attachments: list = None) -> dict:
    """Core SMTP sending logic using Gmail with a single attempt."""
    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["To"] = to_email

        msg.attach(MIMEText(html_body, "html"))

        if attachments:
            for attr in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(base64.b64decode(attr["content"]))
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {attr['filename']}",
                )
                msg.attach(part)

        # Use a timeout for the SMTP connection
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        
        # LOG SUCCESS ONLY ONCE THE MESSAGE IS SENT
        logger.info(f"[EMAIL SUCCESS] Mail definitely accepted by relay for {to_email}")
        _audit_email_event(
            "EMAIL_SEND_SUCCESS",
            to_email=to_email,
            details={
                "provider": "smtp",
                "smtp_host": settings.smtp_host,
                "smtp_port": settings.smtp_port,
            },
        )
        return {"success": True, "error": None}
    except Exception as e:
        error_msg = str(e)
        deferred = _is_gmail_quota_error(e)
        logger.error(
            f"[EMAIL ATTEMPT FAILED] provider=smtp to={to_email} deferred={deferred} "
            f"exc_class={e.__class__.__name__} error={error_msg}",
            exc_info=True,
        )
        _audit_email_event(
            "EMAIL_SEND_FAILED",
            to_email=to_email,
            details={
                "provider": "smtp",
                "deferred": deferred,
                "exc_class": e.__class__.__name__,
                "error": error_msg[:800],
            },
        )
        return {"success": False, "error": error_msg, "deferred": deferred}

async def _send_via_resend(to_email: str, subject: str, html_body: str) -> dict:
    """
    Send an HTML email via Resend's HTTP API.
    Note: for now we don't implement attachments here.
    """
    try:
        api_key = getattr(settings, "resend_api_key", "") or ""
        if not api_key:
            return {"success": False, "error": "RESEND_API_KEY not configured"}

        # Resend is explicit opt-in: require RESEND_FROM to avoid unverified sender domains.
        from_email = getattr(settings, "resend_from", "") or ""
        if not from_email:
            return {"success": False, "error": "RESEND_FROM not configured (Resend disabled)"}

        payload = {
            "from": from_email,
            "to": to_email,
            "subject": subject,
            "html": html_body,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post("https://api.resend.com/emails", json=payload, headers=headers)

        if resp.status_code in (200, 201):
            logger.info(f"[EMAIL SUCCESS] Resend accepted message for {to_email}")
            _audit_email_event(
                "EMAIL_SEND_SUCCESS",
                to_email=to_email,
                details={
                    "provider": "resend",
                    "status_code": resp.status_code,
                },
            )
            return {"success": True, "error": None}

        # Avoid returning huge bodies to logs.
        err_preview = (resp.text or "").strip()[:500]
        logger.error(
            f"[EMAIL ATTEMPT FAILED] provider=resend to={to_email} http_status={resp.status_code} "
            f"error_preview={err_preview}"
        )
        _audit_email_event(
            "EMAIL_SEND_FAILED",
            to_email=to_email,
            details={
                "provider": "resend",
                "status_code": resp.status_code,
                "error_preview": err_preview,
            },
        )
        return {"success": False, "error": f"Resend failed with HTTP {resp.status_code}", "status_code": resp.status_code}
    except Exception as e:
        logger.error(f"[EMAIL ATTEMPT FAILED] Resend {to_email}: {e}", exc_info=True)
        _audit_email_event(
            "EMAIL_SEND_FAILED",
            to_email=to_email,
            details={
                "provider": "resend",
                "exc_class": e.__class__.__name__,
                "error": str(e)[:800],
            },
        )
        return {"success": False, "error": str(e)}

async def send_email_async(to_email: str, subject: str, html_body: str, attachments: list = None) -> dict:
    """Async wrapper for the SMTP sender with up to 2 retries (3 total attempts)."""
    # Attachments: keep SMTP path for now (Resend implementation is HTML-only).
    if attachments:
        loop = asyncio.get_running_loop()
        max_retries = 2
        last_error = "Unknown error"

        for attempt in range(max_retries + 1):
            result = await loop.run_in_executor(
                None,
                _send_via_smtp,
                to_email,
                subject,
                html_body,
                attachments,
            )
            if result["success"]:
                return {**result, "provider": "smtp"}

            if result.get("deferred"):
                return {
                    "success": False,
                    "provider": "smtp",
                    "deferred": True,
                    "error": result.get("error") or "Deferred due to SMTP quota",
                }

            last_error = result["error"]
            if attempt < max_retries:
                wait_time = (attempt + 1) * 2  # Exponential-ish backoff: 2s, 4s
                logger.warning(f"Retrying SMTP email to {to_email} in {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
                await asyncio.sleep(wait_time)

        return {"success": False, "provider": "smtp", "error": f"Failed after {max_retries + 1} attempts: {last_error}", "deferred": False}

    # No attachments:
    # Resend is explicit opt-in and only used when BOTH RESEND_API_KEY and RESEND_FROM are set.
    resend_api_key = (getattr(settings, "resend_api_key", "") or "").strip()
    resend_from = (getattr(settings, "resend_from", "") or "").strip()
    if resend_api_key and resend_from:
        smtp_configured = bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)

        # Retry Resend up to 3 times with 5 second delay
        resend_max_retries = 2
        resend_last_error = "Unknown error"
        for resend_attempt in range(resend_max_retries + 1):
            result = await _send_via_resend(to_email, subject, html_body)
            if result["success"]:
                return {**result, "provider": "resend"}
            resend_last_error = result["error"]
            if resend_attempt < resend_max_retries:
                await asyncio.sleep(5)

        last_error = resend_last_error

        if smtp_configured:
            logger.warning(
                f"[EMAIL FALLBACK TO SMTP] Resend failed for {to_email} ({last_error}); falling back to SMTP."
            )
            loop = asyncio.get_running_loop()
            max_smtp_retries = 2
            smtp_last_error = "Unknown error"
            try:
                for smtp_attempt in range(max_smtp_retries + 1):
                    smtp_result = await loop.run_in_executor(
                        None,
                        _send_via_smtp,
                        to_email,
                        subject,
                        html_body,
                        None,
                    )
                    if smtp_result["success"]:
                        return {**smtp_result, "provider": "smtp"}
                    if smtp_result.get("deferred"):
                        return {
                            "success": False,
                            "provider": "smtp",
                            "deferred": True,
                            "error": smtp_result.get("error") or "Deferred due to SMTP quota",
                        }
                    smtp_last_error = smtp_result["error"]
                    if smtp_attempt < max_smtp_retries:
                        wait_time = (smtp_attempt + 1) * 2
                        await asyncio.sleep(wait_time)
            except Exception as e:
                # Never crash request flow due to email issues.
                logger.error(f"[EMAIL FALLBACK TO SMTP] SMTP fallback crashed: {e}", exc_info=True)
            return {"success": False, "provider": "smtp", "error": f"Failed after SMTP fallback: {smtp_last_error}", "deferred": False}

        return {"success": False, "provider": "resend", "error": f"Failed after Resend attempt: {last_error}", "deferred": False}

    # Fallback: SMTP (original behavior).
    loop = asyncio.get_running_loop()
    max_retries = 2
    last_error = "Unknown error"

    for attempt in range(max_retries + 1):
        result = await loop.run_in_executor(
            None,
            _send_via_smtp,
            to_email,
            subject,
            html_body,
            attachments,
        )
        if result["success"]:
            return {**result, "provider": "smtp"}

        if result.get("deferred"):
            return {
                "success": False,
                "provider": "smtp",
                "deferred": True,
                "error": result.get("error") or "Deferred due to SMTP quota",
            }

        last_error = result["error"]
        if attempt < max_retries:
            wait_time = (attempt + 1) * 2  # Exponential-ish backoff: 2s, 4s
            logger.warning(f"Retrying SMTP email to {to_email} in {wait_time}s (Attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(wait_time)

    return {"success": False, "provider": "smtp", "error": f"Failed after {max_retries + 1} attempts: {last_error}", "deferred": False}

async def execute_email_with_retries(
    to_email: str, 
    subject: str, 
    body: str, 
    application: Any = None, 
    max_retries: int = 3,
    event_type: str = "GENERIC",
    attachments: list = None
):
    """Production-grade email wrapper with persistent idempotency and retries."""
    event_id = str(uuid.uuid4())[:8]
    logger.info(f"[EMAIL][QUEUE] {event_type} (Event: {event_id}) for {_safe_email_target(to_email)}")
    
    # 1. Atomic Idempotency Check (Persistent)
    if application and hasattr(application, 'id'):
        try:
            from app.infrastructure.database import SessionLocal
            from app.domain.models import Application
            from sqlalchemy import update, and_
            with SessionLocal() as db:
                # Atomically set to 'processing' ONLY if not already processing/sent
                stmt = (
                    update(Application)
                    .where(and_(
                        Application.id == application.id,
                        Application.email_status != 'processing',
                        Application.email_status != 'sent'
                    ))
                    .values(email_status='processing')
                )
                res = db.execute(stmt)
                db.commit()
                if res.rowcount == 0:
                    logger.warning(f"[EMAIL][SKIPPED] Atomic duplicate prevented (Event: {event_id}) for App #{application.id}")
                    return True
        except Exception as db_err:
            logger.warning(f"[EMAIL][ATOMIC_GUARD_FAILED] Fallback to runtime check (Event: {event_id}): {db_err}")
            if hasattr(application, 'email_sent_at') and application.email_sent_at:
                return True

    # 2. Retry Loop
    for attempt in range(max_retries):
        try:
            result = await send_email_async(to_email, subject, body, attachments)
            if result["success"]:
                logger.info(f"[EMAIL][EXECUTED] (Event: {event_id}) successfully sent to {_safe_email_target(to_email)}")
                
                # 3. Update Persistence
                if application and hasattr(application, 'id'):
                    try:
                        from app.infrastructure.database import SessionLocal
                        from app.domain.models import Application
                        from sqlalchemy import update
                        with SessionLocal() as db:
                            db.execute(
                                update(Application)
                                .where(Application.id == application.id)
                                .values(email_sent_at=datetime.utcnow(), email_status='sent')
                            )
                            db.commit()
                    except Exception as db_err:
                        logger.warning(f"[EMAIL][DB_UPDATE_FAILED] Could not persist status (Event: {event_id}): {db_err}")
                
                return True
            
            error_msg = result.get("error")
            logger.warning(f"[EMAIL][RETRY] (Event: {event_id}) Attempt {attempt+1}/{max_retries} failed: {error_msg}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt) # Exponential backoff
            
        except Exception as e:
            logger.error(f"[EMAIL][RETRY_ERROR] (Event: {event_id}) Unexpected error: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)

    # 4. Final Failure Update
    if application and hasattr(application, 'id'):
        try:
            from app.infrastructure.database import SessionLocal
            from app.domain.models import Application
            from sqlalchemy import update
            with SessionLocal() as db:
                db.execute(
                    update(Application)
                    .where(Application.id == application.id)
                    .values(email_status='failed')
                )
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to update email status for application {application.id}: {e}")

    logger.error(f"[EMAIL][PERMANENT_FAILURE] (Event: {event_id}) Failed after {max_retries} attempts for {to_email}")
    return False

# --- Email Templates ---

async def send_otp_email(to_email: str, otp: str):
    subject = "Verify your account for the Recruitment System"
    body = f"""
    <html><body>
      <h2>Account Verification</h2>
      <p>Use the OTP below to verify your account. Expires in 30 minutes.</p>
      <h3 style="background:#f4f4f4; padding:10px; display:inline-block; letter-spacing:5px;">{otp}</h3>
    </body></html>
    """
    return await execute_email_with_retries(to_email, subject, body, event_type="OTP_VERIFICATION")

async def send_password_reset_email(to_email: str, otp: str):
    subject = "Password Reset Request"
    frontend_url = settings.frontend_base_url
    reset_link = f"{frontend_url}/auth/reset-password?email={to_email}&otp={otp}"
    body = f"""
    <html><body style="font-family:sans-serif; color:#333;">
      <h2>Password Reset</h2>
      <p>We received a request to reset your password. Use the OTP below to proceed, or click the button to go directly to the reset page. This OTP will expire in 30 minutes.</p>
      <div style="margin: 20px 0; text-align: center;">
        <h3 style="background:#f4f4f4; padding:15px; display:inline-block; letter-spacing:5px; border-radius:5px; border:1px solid #ddd;">{otp}</h3>
      </div>
      <div style="margin: 20px 0; text-align: center;">
        <a href="{reset_link}" style="background-color: #2563eb; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">Reset Password</a>
      </div>
      <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
      <p><a href="{reset_link}">{reset_link}</a></p>
      <p>If you did not request this, please ignore this email.</p>
    </body></html>
    """
    return await execute_email_with_retries(to_email, subject, body, event_type="PASSWORD_RESET")

async def send_application_received_email(to_email_or_app: Any, job_title: str = None):
    if hasattr(to_email_or_app, 'candidate_email'):
        to_email = to_email_or_app.candidate_email
        job_title = to_email_or_app.job.title
    else:
        to_email = to_email_or_app
        
    subject = f"Application Received: {job_title}"
    body = f"""
    <html><body>
      <h2>Thank You for Applying!</h2>
      <p>We received your application for <strong>{job_title}</strong>.</p>
      <p>Our team will review your profile shortly!</p>
    </body></html>
    """
    return await execute_email_with_retries(
        to_email, subject, body, 
        application=to_email_or_app if hasattr(to_email_or_app, 'id') else None,
        event_type="APP_RECEIVED"
    )

async def send_interview_invitation_email(application: Any, raw_access_key: str = ""):
    """Wrapper for send_approved_for_interview_email to match requested pattern."""
    if not raw_access_key:
        # Fallback to current access key if not provided
        if application.interview:
            # We don't have the raw key here, but this is a safety fallback
            pass
            
    # Production refinement: pass the whole application object for persistence
    # This matches the execute_email_with_retries signature
    subject = f"Congratulations! You're invited to interview for {application.job.title}"
    frontend_url = settings.frontend_base_url
    access_url = f"{frontend_url}/interview/access?email={application.candidate_email}&key={raw_access_key}"
    support_url = f"{frontend_url}/support?{urlencode({'email': application.candidate_email, 'access_key': raw_access_key})}"
    
    body = f"""
    <html><body style="font-family:sans-serif; color:#333; line-height:1.6;">
      <h2 style="color:#2563eb;">Interview Invitation</h2>
      <p>Your application for <strong>{application.job.title}</strong> has been approved!</p>
      <p>Please use the secure link below to access the interview portal. This link is unique to you.</p>
      <div style="margin: 20px 0; text-align: center;">
        <a href="{access_url}" style="background-color: #2563eb; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">Begin Interview</a>
      </div>
      <p>If the button doesn't work, copy and paste this link into your browser:</p>
      <p><a href="{access_url}" style="color:#2563eb; word-break:break-all;">{access_url}</a></p>
      <hr style="border:none; border-top:1px solid #eee; margin: 24px 0;"/>
      <div style="background:#f8fafc; border-left:4px solid #f59e0b; padding:16px; border-radius:4px; margin-bottom:16px;">
        <p style="margin:0 0 8px 0; font-weight:700; color:#92400e;">&#128197; Need to Reschedule?</p>
        <p style="margin:0 0 8px 0; color:#555;">If you are unable to attend the interview at this time or encountered a technical issue, please contact us via the Support Portal below.</p>
        <p style="margin:0;">
          👉 <a href="{support_url}" style="color:#2563eb; font-weight:700;">Support Portal &amp; Reschedule Request</a>
        </p>
      </div>
      <p style="font-size:0.9em; color:#888;">If you did not apply for this role, please disregard this email.</p>
    </body></html>
    """
    
    return await execute_email_with_retries(
        application.candidate_email, 
        subject, 
        body, 
        application=application,
        event_type="INTERVIEW_INVITE"
    )

async def send_approved_for_interview_email(to_email: str, job_title: str, raw_access_key: str = ""):
    subject = f"Congratulations! You're invited to interview for {job_title}"
    frontend_url = settings.frontend_base_url
    try:
        parsed = urlparse(frontend_url)
        base = parsed.netloc or frontend_url
        logger.debug(f"Generated interview link base: {base}")
    except Exception:
        pass
    access_url = f"{frontend_url}/interview/access?email={to_email}&key={raw_access_key}"
    support_url = f"{frontend_url}/support?{urlencode({'email': to_email, 'access_key': raw_access_key})}"
    body = f"""
    <html><body style="font-family:sans-serif; color:#333;">
      <h2>Interview Invitation</h2>
      <p>Your application for <strong>{job_title}</strong> has been approved!</p>
      <p>Please use the secure link below to access the interview portal. This link is unique to you and expires in 10 days.</p>
      <div style="margin: 20px 0; text-align: center;">
        <a href="{access_url}" style="background-color: #2563eb; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">Begin Interview</a>
      </div>
      <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
      <p><a href="{access_url}" style="color:#2563eb;">{access_url}</a></p>
      <hr style="border:none; border-top:1px solid #eee; margin: 20px 0;"/>
      <p style="margin: 0 0 6px 0; font-weight:600;">Need help with your interview experience?</p>
      <p style="margin: 0 0 8px 0;">If you faced a technical issue, unexpected termination, or need to raise a grievance, use the Support Portal:</p>
      <p style="margin: 0 0 12px 0;">
         <a href="{support_url}" style="color:#2563eb; font-weight:700;">Support Portal Link</a>
      </p>
      <p style="margin: 0; font-size:0.95em; color:#555;">Our HR team will review your request promptly and reach out if more details are needed.</p>
      <hr style="border:none; border-top:1px solid #eee; margin: 20px 0;"/>
      <p style="font-size:0.9em; color:#666;">If you did not apply for this role, please disregard this email.</p>
    </body></html>
    """
    # Note: We need the Application object for persistence, but this function only takes email.
    # We rely on send_interview_invitation_email wrapper to pass the application object.
    return await execute_email_with_retries(to_email, subject, body, event_type="INTERVIEW_INVITE")

async def send_hired_email(to_email: str, job_title: str, interview=None, offer_letter_path: str = None):
    subject = "Congratulations! You have been selected"
    body = f"""
    <html><body style="font-family:sans-serif; color:#333;">
      <h2 style="color:#10b981;">Congratulations!</h2>
      <p>You have been selected for the <strong>{job_title}</strong> position!</p>
      <p>Please find your Offer Letter attached.</p>
      <p>Our HR team will contact you within 24-48 hours for onboarding.</p>
      <br><p>Best Regards,<br>The Recruitment Team</p>
    </body></html>
    """
    attachments = []
    if offer_letter_path:
        # 1. Try local disk (legacy support for manual uploads)
        if os.path.exists(offer_letter_path):
            try:
                with open(offer_letter_path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                    attachments.append({
                        "filename": os.path.basename(offer_letter_path),
                        "content": content,
                    })
            except Exception as e:
                logger.error(f"Failed to read local offer letter: {e}")
        
        # 2. Try Cloud Storage (New template-driven flow)
        else:
            try:
                from app.core.storage import download_file
                from app.core.config import get_settings
                settings = get_settings()
                
                logger.info(f"Fetching offer letter from cloud storage: {offer_letter_path}")
                content_bytes = download_file(settings.supabase_bucket_offers, offer_letter_path)
                
                if content_bytes:
                    content_b64 = base64.b64encode(content_bytes).decode("utf-8")
                    attachments.append({
                        "filename": f"Offer_Letter_{os.path.basename(offer_letter_path)}",
                        "content": content_b64,
                    })
                else:
                    logger.error(f"Offer letter not found in bucket {settings.supabase_bucket_offers}: {offer_letter_path}")
            except Exception as e:
                logger.error(f"Cloud storage attachment failed for {offer_letter_path}: {e}")

    return await execute_email_with_retries(
        to_email, subject, body, 
        attachments=attachments if attachments else None,
        event_type="HIRED_NOTICE"
    )

async def send_simple_email(to_email: str, subject: str, message: str):
    """Utility for sending internal/simple notification emails."""
    body = f"<html><body><p>{message}</p></body></html>"
    result = await send_email_async(to_email, subject, body)
    return result["success"]

async def send_offer_letter_email(to_email: str, candidate_name: str, company_name: str, offer_letter_url: str, accept_link: str = "", reject_link: str = ""):
    """
    Sends offer letter email with attachment. 
    Supports both local paths and cloud URLs (will download before attaching).
    """
    subject = f"Offer Letter - {company_name}"
    
    body = f"""
    <html><body style="font-family:sans-serif; color:#333; line-height: 1.6;">
      <h2 style="color: #2563eb;">Hello {candidate_name},</h2>
      <p>Congratulations! We are pleased to offer you a position at <strong>{company_name}</strong>.</p>
      <p>Please find the attached offer letter for your review. We are excited about the possibility of you joining our team!</p>
      
      <div style="margin: 30px 0; padding: 20px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;">
        <h4 style="margin-top: 0;">Please respond to this offer:</h4>
        <a href="{accept_link}" style="background-color: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; margin-right: 15px; display: inline-block;">Accept Offer</a>
        <a href="{reject_link}" style="background-color: #ef4444; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">Reject Offer</a>
      </div>

      <p>If the buttons above do not work, use these links:</p>
      <p>Accept: <a href="{accept_link}">{accept_link}</a></p>
      <p>Reject: <a href="{reject_link}">{reject_link}</a></p>
      
      <br><p>Best Regards,<br>HR Team, {company_name}</p>
    </body></html>
    """
    attachments = []
    if offer_letter_url:
        try:
            # Check if it's a URL or local path
            if offer_letter_url.startswith("http"):
                # Download from Cloud (e.g. Supabase)
                async with httpx.AsyncClient(timeout=30.0) as client:
                    logger.info(f"Downloading offer letter from cloud: {offer_letter_url}")
                    resp = await client.get(offer_letter_url)
                    if resp.status_code == 200:
                        content = base64.b64encode(resp.content).decode("utf-8")
                        attachments.append({
                            "filename": f"Offer_Letter_{candidate_name.replace(' ', '_')}.pdf",
                            "content": content,
                        })
                    else:
                        logger.error(f"Failed to download offer letter for attachment: {resp.status_code}")
            elif os.path.exists(offer_letter_url):
                with open(offer_letter_url, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                    attachments.append({
                        "filename": os.path.basename(offer_letter_url),
                        "content": content,
                    })
        except Exception as e:
            logger.error(f"Email attachment processing failed: {e}")

    return await execute_email_with_retries(
        to_email, subject, body, 
        attachments=attachments if attachments else None,
        event_type="OFFER_LETTER"
    )


async def send_rejected_email(to_email: str, job_title: str, is_ai_auto_reject: bool = False):
    subject = f"Update on your application for {job_title}"
    reason = "we found that your resume did not align closely enough with the job requirements." if is_ai_auto_reject else "we have decided to move forward with other candidates at this time."
    body = f"""
    <html><body>
      <h2>Application Update</h2>
      <p>Thank you for applying to <strong>{job_title}</strong>.</p>
      <p>Unfortunately, {reason}</p>
      <p>We encourage you to apply for future roles that match your skills!</p>
    </body></html>
    """
    return await execute_email_with_retries(to_email, subject, body, event_type="REJECTED_NOTICE")

async def send_call_for_interview_email(to_email: str, job_title: str):
    subject = f"Interview Invitation — {job_title}"
    body = f"""
    <html><body>
      <h2>You're Invited for an Interview!</h2>
      <p>Based on your AI assessment, you're invited for an interview for <strong>{job_title}</strong>.</p>
      <p>Our HR team will contact you shortly to schedule it.</p>
    </body></html>
    """
    result = await send_email_async(to_email, subject, body)
    if not result["success"]:
        logger.warning(f"Call for Interview Email failed for {to_email}: {result['error']}")
    return result["success"]

async def send_ticket_resolved_email(to_email: str, issue_type: str, hr_response: str, job_title: str = "your applied position"):
    subject = f"Support Ticket Update - {job_title}"
    
    # Contextual link: if it was a technical issue or interruption, they probably need to go back to the interview
    link_html = ""
    if issue_type in ["technical", "interruption", "reschedule"]:
        access_url = f"{settings.frontend_base_url}/interview/access?email={to_email}"
        link_html = f"""
        <div style="margin: 20px 0;">
            <a href="{access_url}" style="background-color: #2563eb; color: white; padding: 10px 18px; text-decoration: none; border-radius: 4px; font-weight: bold;">Return to Interview Portal</a>
        </div>
        """

    body = f"""
    <html><body style="font-family:sans-serif; color:#333;">
      <h2 style="color:#2563eb;">Support Ticket Update</h2>
      <p>Your support ticket regarding <strong>{issue_type.replace('_', ' ')}</strong> for the <strong>{job_title}</strong> position has been reviewed.</p>
      <div style="background:#f9f9f9; padding:15px; border-left:4px solid #3b82f6; margin:10px 0;">
        <strong>Resolution:</strong><br/>
        {hr_response}
      </div>
      {link_html}
      <p>Thank you for your patience.</p>
    </body></html>
    """
    result = await send_email_async(to_email, subject, body)
    if not result["success"]:
        logger.warning(f"Ticket Resolved Email failed for {to_email}: {result['error']}")
    return result["success"]

async def send_key_reissued_email(to_email: str, job_title: str, new_key: str, hr_response: str):
    subject = f"Re: Congratulations! You're invited to interview for {job_title}"
    frontend_url = settings.frontend_base_url
    access_url = f"{frontend_url}/interview/access?email={to_email}&key={new_key}"
    body = f"""
    <html><body style="font-family:sans-serif; color:#333; line-height:1.6;">
      <h2 style="color:#2563eb;">Access Key Re-issued</h2>
      <p>Your request for <strong>{job_title}</strong> has been approved.</p>
      <div style="background:#f9f9f9; padding:15px; border-left:4px solid #10b981; margin:10px 0;">{hr_response}</div>
      <p><strong>New Access Key:</strong> <span style="background:#f4f4f4; padding:8px 12px; font-family:monospace; font-weight:bold;">{new_key}</span></p>
      <div style="margin: 25px 0; text-align: center;">
        <a href="{access_url}" style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Resume Interview</a>
      </div>
      <p style="font-size: 0.85em; color: #777;">If the button above doesn't work, copy and paste this link: {access_url}</p>
    </body></html>
    """
    result = await send_email_async(to_email, subject, body)
    if not result["success"]:
        logger.warning(f"Key Reissued Email failed for {to_email}: {result['error']}")
    return result["success"]

async def send_onboarding_reminder_email(to_email: str, candidate_name: str, joining_date: str, job_title: str):
    subject = f"Upcoming Onboarding Reminder: {candidate_name}"
    body = f"""
    <html><body style="font-family:sans-serif; color:#333;">
      <h2>Onboarding Reminder</h2>
      <p>This is a reminder that <strong>{candidate_name}</strong> is scheduled to join the company in 7 days on <strong>{joining_date}</strong> for the <strong>{job_title}</strong> role.</p>
      <p>Please ensure all necessary preparations (IT access, workspace setup) are completed ahead of time.</p>
    </body></html>
    """
    return await execute_email_with_retries(to_email, subject, body, event_type="ONBOARDING_REMINDER")

async def send_joining_confirmation_email(to_email: str, candidate_name: str, job_title: str, candidate_photo_url: str):
    subject = f"Joining Confirmation: {candidate_name}"
    body = f"""
    <html><body style="font-family:sans-serif; color:#333;">
      <h2>Candidate Joined Today</h2>
      <p>This is to confirm that <strong>{candidate_name}</strong> has officially joined the company today for the <strong>{job_title}</strong> role.</p>
      <p>Please find the live photograph of the candidate attached.</p>
    </body></html>
    """
    
    attachments = []
    if candidate_photo_url:
        try:
            if candidate_photo_url.startswith("http"):
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(candidate_photo_url)
                    if resp.status_code == 200:
                        content = base64.b64encode(resp.content).decode("utf-8")
                        attachments.append({
                            "filename": f"Photo_{candidate_name.replace(' ', '_')}.jpg",
                            "content": content,
                        })
                    else:
                        logger.error(f"Failed to download candidate photo for email attachment: {resp.status_code}")
            elif os.path.exists(candidate_photo_url):
                with open(candidate_photo_url, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                    attachments.append({
                        "filename": os.path.basename(candidate_photo_url),
                        "content": content,
                    })
        except Exception as e:
            logger.error(f"Email photo attachment processing failed: {e}")

    return await execute_email_with_retries(
        to_email, subject, body, 
        attachments=attachments if attachments else None,
        event_type="JOINING_CONFIRMATION"
    )
