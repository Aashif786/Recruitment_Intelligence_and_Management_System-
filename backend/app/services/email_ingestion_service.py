import imaplib
import email
from email.header import decode_header
from sqlalchemy.orm import Session
from app.domain.models import AttachmentResume
import os
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)

def fetch_resume_attachments(db: Session, imap_user: str, imap_pass: str):
    """
    Connect to IMAP, fetch UNSEEN emails, extract attachments (PDFs/Docx), 
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
        
        # Select the mailbox you want to check
        mail.select("inbox")
        
        # Search for recent emails (both read and unread) to prevent missing opened/read test emails
        status, messages = mail.search(None, 'ALL')
        if status != "OK":
            return {"success": False, "error": "No emails found in inbox."}

        email_ids = messages[0].split()
        
        # Scan the 30 most recent emails (our strict DB duplicate checking handles skipping instantly)
        if len(email_ids) > 30:
            email_ids = email_ids[-30:]
            
        saved_count = 0
        
        for email_id in email_ids:
            # Fetch the email message by ID
            res, msg = mail.fetch(email_id, "(RFC822)")
            if res != "OK":
                continue
                
            for response_part in msg:
                if isinstance(response_part, tuple):
                    # Parse the bytes email into a message object
                    msg_obj = email.message_from_bytes(response_part[1])
                    
                    # Decode email subject
                    subject, encoding = decode_header(msg_obj["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                        
                    # Get sender email
                    sender = msg_obj.get("From", "")
                    
                    # Extract raw email address (e.g. John Doe <john@gmail.com> -> john@gmail.com)
                    import re
                    match = re.search(r'<([^>]+)>', sender)
                    raw_email = match.group(1).lower().strip() if match else sender.lower().strip()
                    
                    # Smart Duplicate Check: Skip only if they already applied to the same specific job
                    # to allow candidates to apply for different jobs, or for seamless testing.
                    from app.domain.models import Application, Job
                    import re
                    
                    # 1. Parse email body first (supports both multipart and single-part text messages)
                    email_body = ""
                    if msg_obj.is_multipart():
                        for part in msg_obj.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                try:
                                    email_body += part.get_payload(decode=True).decode()
                                except:
                                    pass
                    else:
                        try:
                            email_body = msg_obj.get_payload(decode=True).decode()
                        except:
                            pass

                    # Smart Duplicate Check: Skip if they already applied to the same specific job
                    # Checks BOTH subject and email body for active job code matching
                    combined_text_to_check = f"{str(subject)} {email_body}"
                    job_code_match = re.search(r'JOB-[A-Z0-9]{6}', combined_text_to_check, re.IGNORECASE)
                    target_job = None
                    if job_code_match:
                        extracted_code = job_code_match.group(0).upper().strip()
                        target_job = db.query(Job).filter(Job.job_id == extracted_code, Job.status == 'open').first()
                        
                    if target_job:
                        existing_app = db.query(Application).filter(
                            Application.job_id == target_job.id,
                            Application.candidate_email == raw_email
                        ).first()
                        if existing_app:
                            continue # Skip duplicate application for this specific job
                    else:
                        # Fallback: avoid double-fetching if they already have an unprocessed resume
                        has_pending = db.query(AttachmentResume).filter(
                            AttachmentResume.sender_email.ilike(f"%{raw_email}%"),
                            AttachmentResume.processed == False
                        ).first()
                        if has_pending:
                            continue
                    
                    # 2. Extract and process attachments
                    if msg_obj.is_multipart():
                        for part in msg_obj.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            # Extract attachment
                            if content_disposition and ("attachment" in content_disposition or "inline" in content_disposition):
                                filename = part.get_filename()
                                if filename:
                                    # Decode filename
                                    filename, encoding = decode_header(filename)[0]
                                    if isinstance(filename, bytes):
                                        filename = filename.decode(encoding if encoding else "utf-8")
                                        
                                    # Filter: Check if email is job related
                                    search_text = (str(subject) + " " + email_body).lower()
                                    keywords = ["apply", "application", "job", "resume", "internship", "hiring", "career", "cv", "developer", "engineer"]
                                    is_job_related = any(k in search_text for k in keywords) or filename.lower().endswith((".pdf", ".doc", ".docx"))
                                    
                                    if not is_job_related:
                                        continue
                                        
                                    file_data = part.get_payload(decode=True)
                                    if file_data and (filename.lower().endswith(".pdf") or filename.lower().endswith(".doc") or filename.lower().endswith(".docx")):
                                        
                                        # Advanced Duplicate Check: Phone & Resume Name
                                        from app.core.phone_utils import compute_phone_hash, normalize_phone_digits
                                        phone_matches = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', email_body)
                                        is_duplicate = False
                                        for p in phone_matches:
                                            norm_p, _ = normalize_phone_digits(p)
                                            if norm_p and len(norm_p) >= 10:
                                                p_hash = compute_phone_hash(norm_p)
                                                if db.query(Application).filter(Application.candidate_phone_hash == p_hash).first():
                                                    is_duplicate = True
                                                    break
                                                    
                                        # Check if exact same resume file was already ingested across the platform
                                        if not is_duplicate and db.query(AttachmentResume).filter(AttachmentResume.file_name == filename).first():
                                            is_duplicate = True
                                            
                                        if is_duplicate:
                                            continue
                                            
                                        # Save to Supabase Storage Bucket
                                        import time
                                        from app.core.storage import upload_file, get_public_url
                                        
                                        safe_sender = sender.replace("<", "").replace(">", "").replace(" ", "_").split("@")[0]
                                        safe_filename = filename.replace(" ", "_")
                                        storage_path = f"ingested/{safe_sender}_{int(time.time())}_{safe_filename}"
                                        
                                        # Upload to 'MAIL_ATTACHMENTS' bucket
                                        upload_res = upload_file('MAIL_ATTACHMENTS', storage_path, file_data, content_type)
                                        
                                        file_url = None
                                        if upload_res:
                                            file_url = get_public_url('MAIL_ATTACHMENTS', storage_path)
                                        
                                        # Save to DB (skip large binary data to keep table lightweight)
                                        new_resume = AttachmentResume(
                                            sender_email=sender,
                                            subject=subject,
                                            file_name=filename,
                                            file_url=file_url,
                                            file_data=None, # Keep DB lightweight
                                            email_body=email_body, # Store what they wrote in the email
                                            mime_type=content_type
                                        )
                                        db.add(new_resume)
                                        saved_count += 1
                                        
            # Commit after each email to save progress incrementally
            db.commit()
        mail.logout()
        
        return {"success": True, "count": saved_count}
        
    except Exception as e:
        logger.error(f"IMAP Error: {e}")
        return {"success": False, "error": str(e)}


import requests
import hashlib
import re
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
            continue
            
        try:
            # 1. Map to target Job strictly by Job Code (JOB-XXXXXX) or Job ID
            target_job = None
            subject_str = resume.subject or ""
            body_str = resume.email_body or ""
            subject_lower = subject_str.lower()
            body_lower = body_str.lower()
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

            # Pattern D: Smart token-based fuzzy keyword matching
            if not target_job:
                stopwords = {"and", "or", "the", "for", "with", "a", "an", "in", "of", "to", "at", "by", "from", "on", "role", "position", "job", "application", "opportunity", "hiring", "pvt", "ltd", "engineering", "technologies", "recruitment", "engineer", "designer", "developer", "modeller", "modeler", "specialist"}
                best_match = None
                max_score = 0
                for job in open_jobs:
                    # Tokenize job title and filter stopwords
                    job_tokens = set(re.findall(r'[a-z0-9]+', job.title.lower())) - stopwords
                    if not job_tokens:
                        continue
                    # Check how many tokens match the email subject/body
                    matches = sum(1 for token in job_tokens if token in combined_text_lower)
                    score = matches / len(job_tokens)
                    if matches > 0 and score > max_score and score >= 0.4:
                        max_score = score
                        best_match = job
                if best_match:
                    target_job = best_match
                    logger.info(f"Successfully fuzzy mapped emailed resume {resume.id} to Job '{best_match.title}' (score={max_score:.2f})")
                        
            if not target_job:
                logger.warning(
                    f"Emailed resume {resume.id} skipped: No matching open Job ID, Code, or Role Title found in email "
                    f"(Subject: '{resume.subject}')."
                )
                resume.processed = False
                continue
                
            # 2. Extract Candidate Information
            sender_str = resume.sender_email or ""
            # Sender might be: "John Doe <john@gmail.com>"
            name_match = re.search(r'^([^<]+)', sender_str)
            candidate_name = name_match.group(1).strip() if name_match else "Emailed Candidate"
            if not candidate_name or candidate_name.lower() == "emailed candidate":
                # Fallback to email prefix
                email_match = re.search(r'<([^>]+)>', sender_str)
                raw_email = email_match.group(1).lower().strip() if email_match else sender_str.lower().strip()
                candidate_name = raw_email.split('@')[0].replace('.', ' ').title()
            else:
                email_match = re.search(r'<([^>]+)>', sender_str)
                raw_email = email_match.group(1).lower().strip() if email_match else sender_str.lower().strip()
                
            # Extract phone if present in body
            phone_matches = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', body_lower)
            candidate_phone_normalized = None
            candidate_phone_hash = None
            candidate_phone_raw = None
            if phone_matches:
                candidate_phone_raw = phone_matches[0]
                norm_p, _ = normalize_phone_digits(candidate_phone_raw)
                if norm_p and len(norm_p) >= 10:
                    candidate_phone_normalized = norm_p
                    candidate_phone_hash = compute_phone_hash(norm_p)
                    
            # 3. Determine Storage Path from public URL
            resume_file_path = None
            if "/MAIL_ATTACHMENTS/" in resume.file_url:
                bucket_path = resume.file_url.split("/MAIL_ATTACHMENTS/")[-1].split("?")[0]
                resume_file_path = f"MAIL_ATTACHMENTS/{bucket_path}"
                
            # Download file to calculate hash (required by Application model)
            content = b""
            response = requests.get(resume.file_url)
            if response.status_code == 200:
                content = response.content
            resume_hash = hashlib.sha256(content).hexdigest() if content else "dummy_hash_" + str(resume.id)
            
            # Check if this candidate already applied for this job to prevent database errors
            from sqlalchemy import or_
            existing_app = db.query(Application).filter(
                Application.job_id == target_job.id,
                or_(
                    Application.candidate_email == raw_email,
                    (Application.candidate_phone_hash == candidate_phone_hash) if candidate_phone_hash else False
                )
            ).first()
            
            if existing_app:
                # Mark as processed and skip
                resume.processed = True
                continue
                
            # 4. Create the Application Record
            new_application = Application(
                job_id=target_job.id,
                hr_id=target_job.hr_id,
                candidate_name=candidate_name,
                candidate_email=raw_email,
                candidate_phone_normalized=candidate_phone_normalized,
                candidate_phone_raw=candidate_phone_raw,
                candidate_phone_hash=candidate_phone_hash,
                resume_file_name=resume.file_name,
                resume_hash=resume_hash,
                resume_file_path=resume_file_path,
                status="applied",
                applied_at=datetime.now(),
                resume_status="pending",
                hr_notes="Ingested automatically from Email Recruiter Channel."
            )
            
            db.add(new_application)
            db.commit()
            db.refresh(new_application)
            
            # 5. Trigger the Background AI Analysis Pipeline
            from app.api.applications import process_application_background
            import asyncio
            
            # Run the heavy AI analysis in an isolated background task so a parsing error/conflict does not block or roll back other applications in the batch
            asyncio.create_task(
                process_application_background(
                    new_application.id,
                    target_job.id,
                    new_application.resume_file_path,
                    raw_email,
                    candidate_name
                )
            )
            
            resume.processed = True
            processed_count += 1
            
        except Exception as e:
            logger.error(f"Error automapping emailed resume {resume.id} to application: {e}")
            db.rollback()
            
    db.commit()
    return {"message": f"Successfully mapped and AI analyzed {processed_count} resumes.", "count": processed_count}
