import imaplib
import email
from email.header import decode_header
from sqlalchemy.orm import Session
from app.domain.models import AttachmentResume
import os
import logging
import re
from app.core.config import get_settings

logger = logging.getLogger(__name__)

def fetch_resume_attachments(db: Session, imap_user: str, imap_pass: str):
    """
    Connect to IMAP, fetch emails, extract attachments (PDFs/Docx), 
    and store them into the AttachmentResume table.
    """
    if not imap_user or not imap_pass:
        logger.error("IMAP credentials not provided.")
        return {"success": False, "error": "IMAP credentials missing."}

    # Gmail IMAP server
    imap_server = "imap.gmail.com"
    
    try:
        # Create an IMAP4 class with SSL 
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(imap_user, imap_pass)
        
        # Select the mailbox (INBOX is the standard for Gmail)
        mail.select("INBOX")
        
        # Search for ALL emails (Read and Unread) to ensure we don't miss test emails
        status, messages = mail.search(None, 'ALL')
        if status != "OK":
            return {"success": False, "error": "Could not access inbox."}

        email_ids = messages[0].split()
        
        # Scan the 10 most recent emails (our strict DB duplicate checking handles skipping instantly, but 10 prevents Gmail throttling)
        if len(email_ids) > 10:
            email_ids = email_ids[-10:]
            
        saved_count = 0
        logger.info(f"Scanning {len(email_ids)} emails for resume attachments...")
        
        for email_id in reversed(email_ids): # Process newest first
            try:
                # 1. Fetch only Header metadata first
                res, msg_meta = mail.fetch(email_id, "(BODY[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)])")
                if res != "OK":
                    logger.warning(f"Failed to fetch metadata for email ID {email_id}")
                    continue
                
                header_obj = email.message_from_bytes(msg_meta[0][1])
                msg_id = (header_obj.get("Message-ID") or "").strip()
                subject, encoding = decode_header(header_obj["Subject"] or "")[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                sender = header_obj.get("From", "")
                match = re.search(r'<([^>]+)>', sender)
                raw_email = match.group(1).lower().strip() if match else sender.lower().strip()
                
                # Parse Date header
                date_str = header_obj.get("Date")
                received_at = None
                if date_str:
                    try:
                        from email.utils import parsedate_to_datetime
                        received_at = parsedate_to_datetime(date_str)
                    except Exception as e:
                        logger.warning(f"Failed to parse date '{date_str}': {e}")

                # Fast Duplicate Check: Message-ID is globally unique
                from sqlalchemy import or_
                dup_filter = []
                if msg_id:
                    dup_filter.append(AttachmentResume.message_id == msg_id)
                
                # Only use subject/sender fallback if we have a subject and sender
                if raw_email and subject:
                    dup_filter.append((AttachmentResume.sender_email.ilike(f"%{raw_email}%")) & (AttachmentResume.subject == subject))
                
                if dup_filter:
                    existing_attachment = db.query(AttachmentResume).filter(or_(*dup_filter)).first()
                    if existing_attachment:
                        logger.info(f"Skipping duplicate email: {subject} from {raw_email}")
                        continue

                # 2. Only fetch full RFC822 if metadata check passes
                res, msg = mail.fetch(email_id, "(RFC822)")
                if res != "OK":
                    logger.warning(f"Failed to fetch full content for email ID {email_id}")
                    continue
                    
                for response_part in msg:
                    if isinstance(response_part, tuple):
                        msg_obj = email.message_from_bytes(response_part[1])
                        
                        # Parse email body
                        email_body = ""
                        if msg_obj.is_multipart():
                            for part in msg_obj.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    try:
                                        payload = part.get_payload(decode=True)
                                        if payload:
                                            email_body += payload.decode()
                                    except:
                                        pass
                        else:
                            try:
                                payload = msg_obj.get_payload(decode=True)
                                if payload:
                                    email_body = payload.decode()
                            except:
                                pass

                        # Extract and process attachments
                        found_resume = False
                        if msg_obj.is_multipart():
                            for part in msg_obj.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                
                                if content_disposition and ("attachment" in content_disposition or "inline" in content_disposition):
                                    filename = part.get_filename()
                                    if filename:
                                        filename, encoding = decode_header(filename)[0]
                                        if isinstance(filename, bytes):
                                            filename = filename.decode(encoding if encoding else "utf-8")
                                            
                                        # Filter: Check if attachment is a resume
                                        is_resume = filename.lower().endswith((".pdf", ".doc", ".docx"))
                                        
                                        if not is_resume:
                                            continue
                                            
                                        file_data = part.get_payload(decode=True)
                                        if file_data:
                                            # Save to Supabase Storage Bucket
                                            import time
                                            from app.core.storage import upload_file, get_public_url
                                            
                                            safe_sender = raw_email.split("@")[0].replace(".", "_")
                                            safe_filename = re.sub(r'[^\w\.-]', '_', filename)
                                            storage_path = f"ingested/{safe_sender}_{int(time.time())}_{safe_filename}"
                                            
                                            upload_res = upload_file('MAIL_ATTACHMENTS', storage_path, file_data, content_type)
                                            
                                            file_url = None
                                            if upload_res:
                                                file_url = get_public_url('MAIL_ATTACHMENTS', storage_path)
                                            
                                            new_resume = AttachmentResume(
                                                message_id=msg_id,
                                                sender_email=sender,
                                                subject=subject,
                                                file_name=filename,
                                                file_url=file_url,
                                                file_data=None, 
                                                email_body=email_body,
                                                mime_type=content_type,
                                                received_at=received_at
                                            )
                                            db.add(new_resume)
                                            saved_count += 1
                                            found_resume = True
                                            logger.info(f"Ingested new resume from {raw_email}: {filename}")
                        
                        if not found_resume:
                            logger.info(f"Email from {raw_email} had no resume attachments.")
                
                # Commit incrementally
                db.commit()

            except Exception as e:
                logger.error(f"Error processing email {email_id}: {e}", exc_info=True)
                db.rollback()

        mail.close()
        mail.logout()
        return {"success": True, "count": saved_count}
        
    except Exception as e:
        logger.error(f"IMAP Error: {e}")
        return {"success": False, "error": str(e)}


import requests
import hashlib
from datetime import datetime
from app.domain.models import Application, Job
from app.core.phone_utils import compute_phone_hash, normalize_phone_digits

async def run_batch_resume_processing(db: Session):
    """
    Finds all unprocessed resumes from the email ingestion database,
    automatically creates target Job Applications for them, and triggers the AI analysis pipeline.
    """
    # Process in sequential batches of 30 to respect system limits and distribute workload
    unprocessed = db.query(AttachmentResume).filter(
        AttachmentResume.processed == False
    ).order_by(AttachmentResume.id.asc()).limit(30).all()
    
    if not unprocessed:
        return {"message": "No new resumes to process.", "count": 0}
        
    open_jobs = db.query(Job).filter(Job.status == 'open').all()
    if not open_jobs:
        logger.warning("No open jobs available to assign incoming emailed resumes to.")
        return {"message": "No open jobs to map resumes.", "count": 0}
        
    processed_count = 0
    
    for resume in unprocessed:
        if not resume.file_url:
            resume.processed = True  # Skip ones without URLs
            db.commit()
            continue
            
        try:
            # 1. Map to target Job strictly by Job Code (JOB-XXXXXX) or Job ID
            target_job = None
            subject_str = resume.subject or ""
            body_str = resume.email_body or ""
            combined_text_raw = f"{subject_str} {body_str}"
            combined_text_lower = combined_text_raw.lower()
            
            # Pattern A: Match Job Code (e.g., JOB-BVFUPH)
            job_code_match = re.search(r'JOB-[A-Z0-9]{6}', combined_text_raw, re.IGNORECASE)
            if job_code_match:
                extracted_code = job_code_match.group(0).upper().strip()
                target_job = db.query(Job).filter(Job.job_id == extracted_code, Job.status == 'open').first()
                if target_job:
                    logger.info(f"Successfully mapped emailed resume {resume.id} to Job Code {extracted_code}")
            
            # Pattern B: Match numeric Job ID (e.g. "job id: 3", "job id - 3", "job id 3")
            if not target_job:
                numeric_id_match = re.search(r'job\s*(?:id|code)?\s*[:\-\#]?\s*([0-9]+)', combined_text_lower)
                if numeric_id_match:
                    extracted_id = int(numeric_id_match.group(1).strip())
                    target_job = db.query(Job).filter(Job.id == extracted_id, Job.status == 'open').first()
                    if target_job:
                        logger.info(f"Successfully mapped emailed resume {resume.id} to Job ID {extracted_id}")
            
            # Pattern C: Fallback to matching Role Title in the email text
            if not target_job:
                for job in open_jobs:
                    if job.title.lower() in combined_text_lower:
                        target_job = job
                        logger.info(f"Successfully mapped emailed resume {resume.id} to Job Title '{job.title}'")
                        break

            if not target_job:
                logger.warning(f"Could not map emailed resume {resume.id} from {resume.sender_email} to any open job.")
                resume.processed = True # Mark as processed even if not mapped to avoid re-scanning
                db.commit()
                continue

            # 2. Create Application
            # Extract candidate info from sender string
            sender_raw = resume.sender_email
            match = re.search(r'([^<]+)<', sender_raw)
            candidate_name = match.group(1).strip() if match else "Candidate"
            
            match_email = re.search(r'<([^>]+)>', sender_raw)
            candidate_email = match_email.group(1).lower().strip() if match_email else sender_raw.lower().strip()
            
            # Final Duplicate Check: Ensure they haven't already applied to THIS job
            existing_app = db.query(Application).filter(
                Application.job_id == target_job.id,
                Application.candidate_email == candidate_email
            ).first()
            
            if existing_app:
                logger.info(f"Candidate {candidate_email} already has an application for job {target_job.id}. Skipping.")
                resume.processed = True
                db.commit()
                continue

            # Create the application record
            new_app = Application(
                job_id=target_job.id,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                resume_url=resume.file_url,
                status='pending',
                source='email_ingestion',
                applied_at=datetime.utcnow()
            )
            db.add(new_app)
            db.flush() # Get new_app.id
            
            # 3. Trigger Analysis
            from app.services.ai_service import analyze_resume_background
            # We trigger the standard background analysis task
            analyze_resume_background(new_app.id, db)
            
            resume.processed = True
            db.commit()
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Error mapping resume {resume.id}: {e}")
            db.rollback()
            
    return {"message": f"Successfully processed {processed_count} resumes.", "count": processed_count}
