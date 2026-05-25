from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload, contains_eager
from sqlalchemy import func, and_
from typing import List, Dict, Any, Optional
from app.infrastructure.database import get_db
from app.domain.models import User, Job, Application, Interview, InterviewReport, InterviewQuestion, InterviewAnswer
from app.core.auth import get_current_hr
import json
import os
import traceback
from datetime import datetime
import logging
from app.core.config import get_settings
from app.core.storage import get_signed_url

logger = logging.getLogger(__name__)

router = APIRouter()
from fastapi import Request
from app.core.rate_limiter import limiter

@router.get("/config/skills")
@limiter.limit("60/minute")
def get_skills_config(request: Request):
    """Expose the canonical skill categories from the interview engine (Point 1)"""
    try:
        from interview_process.config import SKILL_CATEGORIES
        return list(SKILL_CATEGORIES.keys())
    except Exception as e:
        logger.error(f"Error loading skill categories: {e}")
        # Fallback to a basic list if import fails
        return ["backend", "frontend", "fullstack", "devops", "hr"]

@router.get("/dashboard")
@limiter.limit("60/minute")
def get_dashboard_analytics(
    request: Request, job_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """Get enterprise analytics with filtering support"""
    try:
        from app.services.analytics_service import AnalyticsService
        # Apply visibility isolation
        hr_id = current_user.id if current_user.role.lower() != "super_admin" else None
        
        # Call service with filters
        metadata = AnalyticsService.get_dashboard(
            db, 
            hr_id=hr_id, 
            job_id=job_id,
            from_date=from_date,
            to_date=to_date
        )

        # Standard Success Format
        return {
            "success": True,
            "data": metadata,
            "error": None
        }
    except Exception as e:
        logger.error(f"[ANALYTICS][CRITICAL] {str(e)}")
        # HARD FALLBACK (NO FAILURE EVER)
        return {
            "success": True,
            "data": {
                "total_applications": 0,
                "total_interviews": 0,
                "completed_interviews": 0,
                "success_rate": 0,
                "average_score": 0
            },
            "error": None
        }



@router.get("/reports")
@limiter.limit("60/minute")
def get_interview_reports(
    request: Request, job_id: Optional[int] = None,
    status: Optional[str] = None,
    experience: Optional[str] = None,
    skill: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    score_min: Optional[float] = None,
    score_max: Optional[float] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """
    Get all interview reports. 
    Source of truth: Interviews that are in a 'final' state (completed/terminated) 
    OR Applications that are in 'review_later'.
    """
    try:
        logger.info(f"[REPORTS] Fetching reports: job_id={job_id}, status={status}, exp={experience}, skill={skill}, from={from_date}, to={to_date}, search={search}")
        from sqlalchemy import or_
        # Source of truth is Application, joined with Interview
        query = db.query(Application)\
            .outerjoin(Interview, Application.id == Interview.application_id)\
            .outerjoin(InterviewReport, Interview.id == InterviewReport.interview_id)\
            .outerjoin(Job, Application.job_id == Job.id)
        
        # Filter for "Work that should be reported"
        REPORTABLE_APPLICATION_STATUSES = [
            "interview_completed", "review_later", "hired", "rejected", 
            "offer_sent", "pending_approval", "accepted", "onboarded",
            "physical_interview"
        ]
        
        query = query.filter(or_(
            Interview.status.in_(["completed", "terminated", "expired"]),
            Application.status.in_(REPORTABLE_APPLICATION_STATUSES)
        ))

        # Apply visibility isolation
        if current_user.role.lower() != "super_admin":
            query = query.filter(Application.hr_id == current_user.id)
        
        # Apply Filters
        if job_id and str(job_id).lower() != "all":
            query = query.filter(Application.job_id == job_id)
        
        if status and str(status).lower() != "all":
            status_lower = status.lower()
            if status_lower == "select":
                query = query.filter(or_(Interview.overall_score > 6, InterviewReport.overall_score > 6))
            elif status_lower == "consider":
                query = query.filter(or_(
                    and_(Interview.overall_score > 4, Interview.overall_score <= 6),
                    and_(InterviewReport.overall_score > 4, InterviewReport.overall_score <= 6)
                ))
            elif status_lower == "reject":
                query = query.filter(or_(Interview.overall_score <= 4, InterviewReport.overall_score <= 4))
            elif status_lower == "not completed":
                query = query.filter(or_(Interview.id == None, Interview.status != "completed"))
            elif status_lower == "default":
                pass
            else:
                # Direct application status match
                query = query.filter(Application.status == status)

        if experience and experience != "All":
            from app.domain.models import ResumeExtraction
            exp_val = experience
            if exp_val.lower() == "mid":
                query = query.filter(Application.resume_extraction.has(or_(
                    ResumeExtraction.experience_level.ilike("mid"),
                    ResumeExtraction.experience_level.ilike("mid-level")
                )))
            else:
                query = query.filter(Application.resume_extraction.has(ResumeExtraction.experience_level.ilike(f"%{exp_val}%")))

        if skill and skill != "All":
            from app.domain.models import ResumeExtraction
            skill_space = skill.replace('_', ' ')
            query = query.filter(or_(
                Application.resume_extraction.has(or_(
                    ResumeExtraction.extracted_skills.ilike(f"%{skill}%"),
                    ResumeExtraction.extracted_skills.ilike(f"%{skill_space}%")
                )),
                Interview.locked_skill.ilike(f"%{skill}%"),
                Interview.locked_skill.ilike(f"%{skill_space}%")
            ))

        if search:
            term = f"%{search}%"
            query = query.filter(or_(
                Application.candidate_name.ilike(term),
                Job.title.ilike(term)
            ))

        if from_date:
            try:
                sd = datetime.strptime(from_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                query = query.filter(or_(
                    Interview.created_at >= sd,
                    Application.applied_at >= sd,
                    InterviewReport.created_at >= sd
                ))
            except ValueError:
                pass
        if to_date:
            try:
                ed = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                query = query.filter(or_(
                    Interview.created_at <= ed,
                    Application.applied_at <= ed,
                    InterviewReport.created_at <= ed
                ))
            except ValueError:
                pass

        if score_min is not None:
            query = query.filter(or_(
                Interview.overall_score >= score_min,
                InterviewReport.overall_score >= score_min
            ))
        if score_max is not None:
            query = query.filter(or_(
                Interview.overall_score <= score_max,
                InterviewReport.overall_score <= score_max
            ))

        total = query.with_entities(func.count(Application.id.distinct())).scalar() or 0
        logger.info(f"[REPORTS] Query total: {total}")
        applications = query.options(
            contains_eager(Application.interview).contains_eager(Interview.report),
            contains_eager(Application.job),
            joinedload(Application.hiring_decision),
            joinedload(Application.hr),
            joinedload(Application.resume_extraction)
        ).order_by(Application.applied_at.desc()).offset(skip).limit(limit).all()

        logger.info(f"[REPORTS] Found {len(applications)} applications for HR {current_user.id}")
        
        reports = []
        failed_count = 0
        
        # Pre-fetch all questions/answers for everything in the list
        interview_ids = [app.interview.id for app in applications if app.interview]
        all_questions_map = {}
        all_answers_map = {}
        
        if interview_ids:
            questions = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id.in_(interview_ids)
            ).order_by(InterviewQuestion.interview_id, InterviewQuestion.question_number).all()
            for q in questions:
                all_questions_map.setdefault(q.interview_id, []).append(q)
            
            q_ids = [q.id for q in questions]
            if q_ids:
                answers = db.query(InterviewAnswer).filter(InterviewAnswer.question_id.in_(q_ids)).all()
                for a in answers:
                    all_answers_map[a.question_id] = a

        for app in applications:
            try:
                # Defensive check for related objects
                if not app:
                    continue
                    
                interview = app.interview
                report = interview.report if interview else None
                job = app.job
                
                # 1. Build Profile
                candidate_profile = {
                    "candidate_name": app.candidate_name if app.candidate_name else "Unknown",
                    "candidate_email": app.candidate_email if app.candidate_email else "N/A",
                    "applied_role": job.title if job else "N/A",
                    "experience_level": "N/A",
                    "primary_skill": "general",
                    "skills": [],
                }
                
                # Safe access to resume extraction
                resume = getattr(app, 'resume_extraction', None)
                if resume:
                    candidate_profile["experience_level"] = resume.experience_level or "N/A"
                    candidate_profile["primary_skill"] = resume.extracted_skills or "general"
                    candidate_profile["skills"] = (resume.extracted_skills or "").split(",")

                # 2. Extract Q&A metrics
                question_evaluations = []
                aptitude_evals = []
                
                behavioral_scores = []
                technical_scores = []
                
                if interview:
                    # Use pre-fetched data from maps if available, otherwise fallback
                    interview_questions = all_questions_map.get(interview.id, [])
                    for q in interview_questions:
                        ans = all_answers_map.get(q.id)
                        evaluation = {}
                        if ans:
                            if ans.answer_evaluation:
                                try:
                                    if isinstance(ans.answer_evaluation, str):
                                        if ans.answer_evaluation == "[DECRYPTION_ERROR]":
                                            evaluation = {}
                                        else:
                                            try:
                                                evaluation = json.loads(ans.answer_evaluation)
                                            except:
                                                evaluation = {}
                                    else:
                                        evaluation = ans.answer_evaluation if isinstance(ans.answer_evaluation, dict) else {}
                                except Exception:
                                    evaluation = {}
                            
                            evaluation.setdefault("overall", float(ans.answer_score or 0))
                            base_overall = float(ans.answer_score or 0)
                            q_type_lower = (q.question_type or "technical").lower()
                            if q_type_lower == "behavioral":
                                evaluation.setdefault("relevance", float(ans.technical_score or ans.skill_relevance_score or base_overall))
                                evaluation.setdefault("action_impact", float(ans.completeness_score or base_overall))
                            elif q_type_lower != "aptitude":
                                evaluation.setdefault("technical_accuracy", float(ans.technical_score or ans.skill_relevance_score or base_overall))
                                evaluation.setdefault("completeness", float(ans.completeness_score or base_overall))
                                evaluation.setdefault("depth", float(ans.depth_score or base_overall))

                        q_type = (q.question_type or "technical").lower()
                        entry = {
                            "question": q.question_text,
                            "answer": ans.answer_text if ans else "",
                            "evaluation": evaluation,
                            "score": ans.answer_score if ans else 0,
                            "question_number": q.question_number,
                            "question_type": q_type
                        }

                        if q_type == "aptitude":
                            entry["correct"] = (ans.answer_score >= 5) if ans else False
                            aptitude_evals.append(entry)
                        else:
                            if q_type == "behavioral":
                                behavioral_scores.append(ans.answer_score or 0 if ans else 0)
                            else:
                                technical_scores.append(ans.answer_score or 0 if ans else 0)
                            question_evaluations.append(entry)

                # Fallback to detailed_feedback if no questions found (legacy/report only)
                if not question_evaluations and not aptitude_evals and report and hasattr(report, 'detailed_feedback') and report.detailed_feedback:
                    try:
                        raw_feedback = report.detailed_feedback
                        if raw_feedback != "[DECRYPTION_ERROR]":
                            try:
                                feedback_data = json.loads(raw_feedback) if isinstance(raw_feedback, str) else raw_feedback
                            except:
                                feedback_data = {}
                            
                            feedback_list = []
                            if isinstance(feedback_data, dict):
                                feedback_list = feedback_data.get("question_evaluations", [])
                            elif isinstance(feedback_data, list):
                                feedback_list = feedback_data
                            
                            for idx, q_data in enumerate(feedback_list):
                                q_type = q_data.get("question_type", "technical").lower()
                                entry = {
                                    "question": q_data.get("question", ""),
                                    "answer": q_data.get("answer", ""),
                                    "evaluation": q_data.get("evaluation", {}),
                                    "score": q_data.get("score", q_data.get("evaluation", {}).get("overall", 0)),
                                    "question_number": q_data.get("question_number", idx + 1),
                                    "question_type": q_type
                                }
                                if q_type == "aptitude":
                                    aptitude_evals.append(entry)
                                else:
                                    question_evaluations.append(entry)
                    except:
                        pass

                # Calculate averages for return
                all_q = (question_evaluations or []) + (aptitude_evals or [])
                tech_s = [q.get("score", 0) for q in all_q if q.get("question_type") == "technical" and q.get("score") is not None]
                beh_s = [q.get("score", 0) for q in all_q if q.get("question_type") == "behavioral" and q.get("score") is not None]
                apt_q = aptitude_evals or []
                
                tech_avg = sum(tech_s) / len(tech_s) if tech_s else 0
                beh_avg = sum(beh_s) / len(beh_s) if beh_s else 0
                apt_qty = len(apt_q)
                apt_correct = sum(1 for q in apt_q if q.get("correct") is True)

                apt_score = (apt_correct / apt_qty * 10) if apt_qty > 0 else 0

                # 4. Construct Final Response with Safe Timestamps
                created = None
                # Use getattr for maximum safety against detached objects or missing attributes
                if report and getattr(report, 'created_at', None):
                    created = report.created_at
                elif interview and getattr(interview, 'created_at', None):
                    created = interview.created_at
                elif app and getattr(app, 'applied_at', None):
                    created = app.applied_at
                
                # Identification Fallbacks
                rid = getattr(report, 'id', None) if report else None
                iid = getattr(interview, 'id', None) if interview else None
                aid = getattr(app, 'id', '0')
                
                report_id = rid if rid else (f"skel_{iid}" if iid else f"app_{aid}")
                interview_id = iid
                test_id = getattr(interview, 'test_id', None) if interview else None
                filename = f"report_{iid}.json" if iid else f"app_{aid}.json"
                
                vpath = getattr(interview, 'video_recording_path', None) if interview else None
                video_url = f"/api/interviews/{iid}/video-stream" if iid else None

                # Score fallbacks
                r_overall = getattr(report, 'overall_score', None)
                i_overall = getattr(interview, 'overall_score', None)
                r_combined = getattr(report, 'combined_score', None)
                r_tech = getattr(report, 'technical_skills_score', None)
                r_beh = getattr(report, 'behavioral_score', None)
                r_apt = getattr(report, 'aptitude_score', None)

                reports.append({
                    "id": str(report_id),
                    "interview_id": interview_id,
                    "filename": filename,
                    "test_id": test_id,
                    "timestamp": created.isoformat() if created else datetime.now().isoformat(),
                    "display_date": created.strftime("%Y-%m-%d %H:%M:%S") if created else "",
                    "display_date_short": created.strftime("%b %d, %Y") if created else "",
                    "status": getattr(app, 'status', 'unknown'),
                    "overall_score": float(r_overall if r_overall is not None else (i_overall if i_overall is not None else 0)),
                    "final_score": float(r_combined if r_combined is not None else (i_overall if i_overall is not None else 0)),
                    "technical_score": float(tech_avg if tech_s else (r_tech if r_tech is not None else 0)),
                    "behavioral_score": float(beh_avg if beh_s else (r_beh if r_beh is not None else 0)),
                    "aptitude_score": float(apt_score if apt_qty > 0 else (r_apt if r_apt is not None else 0)),
                    "total_questions_answered": len([e for e in question_evaluations if e.get("answer")]),
                    "aptitude_questions_answered": apt_qty,
                    "question_evaluations": question_evaluations,
                    "aptitude_question_evaluations": aptitude_evals,
                    "candidate_profile": candidate_profile,
                    "recommendation": getattr(report, 'recommendation', 'consider') if report else "consider",
                    "video_url": video_url,
                    "assigned_hr_id": getattr(app, 'hr_id', None),
                    "assigned_hr_name": getattr(app.hr, 'full_name', 'Unknown') if (app and getattr(app, 'hr', None)) else "Unknown",
                    "is_owner": (getattr(app, 'hr_id', None) == current_user.id) if (current_user and hasattr(current_user, 'id')) else False,
                    "termination_reason": getattr(report, 'termination_reason', None)
                })
            except Exception as e:
                # Log specific error and keep going - DO NOT CRASH THE WHOLE LIST
                logger.warning(f"[REPORTS][SKIPPED] Application {getattr(app, 'id', 'unknown')} failed processing: {str(e)}")
                failed_count += 1
                continue

        # Final sort - newest first by timestamp
        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        logger.info(f"[REPORTS] Successfully processed {len(reports)} records for HR {current_user.id} ({failed_count} errors)")
        
        return {
            "reports": reports,
            "total": total,
            "count": len(reports),
            "failed": failed_count,
            "pages": (total + limit - 1) // limit if limit > 0 else 1
        }

    except Exception as e:
        import traceback
        logger.critical(f"CRITICAL ERROR in get_interview_reports: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "reports": [],
            "total": 0,
            "count": 0,
            "failed": 0,
            "pages": 0
        }


@router.get("/interviews")
@limiter.limit("60/minute")
def get_filtered_interviews(
    request: Request, candidate_name: Optional[str] = None,
    candidate_email: Optional[str] = None,
    test_id: Optional[str] = None,
    role_applied: Optional[str] = None,
    search: Optional[str] = None,
    date: Optional[str] = None,
    status: Optional[str] = None,
    job_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_hr),
    db: Session = Depends(get_db)
):
    """
    Get filtered candidates (Applications) for the HR user. 
    Basing this on Applications ensures the list count matches the 'Total Candidates' metric.
    """
    from sqlalchemy.orm import selectinload
    from sqlalchemy import or_, and_
    
    logger.info(f"Filtering interviews: status={status}, job_id={job_id}, search={search}")

    # Source of truth is Application to ensure 100% data alignment with Total Candidates card
    query = db.query(Application)\
        .outerjoin(Job, Application.job_id == Job.id)\
        .outerjoin(Interview, Application.id == Interview.application_id)\
        .options(
            selectinload(Application.job),
            selectinload(Application.interview).selectinload(Interview.report)
        )

    # Apply visibility isolation
    if current_user.role.lower() != "super_admin":
        query = query.filter(Application.hr_id == current_user.id)

    # Filter by Job ID
    if job_id:
        query = query.filter(Application.job_id == job_id)

    # Apply global search if present
    if search:
        query = query.filter(or_(
            Application.candidate_name.ilike(f"%{search}%"),
            Interview.test_id.ilike(f"%{search}%"),
            Job.title.ilike(f"%{search}%")
        ))

    # Apply specific filters
    if candidate_name:
        query = query.filter(Application.candidate_name.ilike(f"%{candidate_name}%"))
    
    if candidate_email:
        query = query.filter(Application.candidate_email.ilike(f"%{candidate_email}%"))
    
    if test_id:
        query = query.filter(Interview.test_id.ilike(f"%{test_id}%"))
    
    if role_applied:
        query = query.filter(Job.title.ilike(f"%{role_applied}%"))
    
    if status and status != "all":
        status_lower = status.lower()
        if status_lower == "hired":
            query = query.filter(Application.status.in_(['hired', 'accepted', 'onboarded']))
        elif status_lower == "completed":
            query = query.filter(or_(
                Interview.status == 'completed',
                and_(Interview.id == None, Application.status == 'interview_completed')
            ))
        elif status_lower == "rejected":
            query = query.filter(Application.status == 'rejected')
        elif status_lower == "not_started":
            # Priority: If interview exists, must be not_started. If not, application must be early stage.
            query = query.filter(or_(
                Interview.status == 'not_started',
                and_(Interview.id == None, Application.status.in_(['applied', 'screened']))
            ))
        elif status_lower == "in_progress":
            # Priority: If interview exists, must be in_progress. If not, application must be in-progress stage.
            query = query.filter(or_(
                Interview.status == 'in_progress',
                and_(Interview.id == None, Application.status.in_(['aptitude_round', 'ai_interview', 'physical_interview']))
            ))
        else:
            # Fallback for any other specific status (e.g., 'terminated', 'cancelled')
            query = query.filter(or_(
                Interview.status == status_lower,
                and_(Interview.id == None, Application.status == status_lower)
            ))
    
    if date:
        try:
            sd = datetime.strptime(date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
            ed = sd.replace(hour=23, minute=59, second=59)
            from sqlalchemy import or_
            query = query.filter(or_(
                Application.applied_at.between(sd, ed),
                Interview.created_at.between(sd, ed)
            ))
        except ValueError:
            pass

    # Order by newest first
    total = query.count()
    applications = query.order_by(Application.applied_at.desc(), Application.id.desc()).offset(skip).limit(limit).all()

    result = []
    for app in applications:
        interview = app.interview
        job = app.job
        
        # Use interview status if it exists, otherwise fallback to application status
        display_status = interview.status if interview else app.status
        
        result.append({
            "id": interview.id if interview else f"app_{app.id}",
            "test_id": interview.test_id if interview else None,
            "candidate_name": app.candidate_name,
            "candidate_email": app.candidate_email,
            "job_title": job.title if job else "Unknown",
            "date": (interview.created_at if interview else app.applied_at).isoformat(),
            "status": display_status,
            "report_id": interview.report.id if (interview and interview.report) else None,
            "assigned_hr_id": app.hr_id,
            "assigned_hr_name": app.hr.full_name if app.hr else "Unknown",
            "is_owner": (app.hr_id == current_user.id)
        })

    return {"items": result, "total": total}

