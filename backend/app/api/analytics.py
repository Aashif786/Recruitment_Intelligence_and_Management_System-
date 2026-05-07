from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
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

@router.get("/config/skills")
def get_skills_config():
    """Expose the canonical skill categories from the interview engine (Point 1)"""
    try:
        from interview_process.config import SKILL_CATEGORIES
        return list(SKILL_CATEGORIES.keys())
    except Exception as e:
        logger.error(f"Error loading skill categories: {e}")
        # Fallback to a basic list if import fails
        return ["backend", "frontend", "fullstack", "devops", "hr"]

@router.get("/dashboard")
def get_dashboard_analytics(
    job_id: Optional[int] = None,
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
def get_interview_reports(
    job_id: Optional[int] = None,
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
        if job_id:
            query = query.filter(Application.job_id == job_id)
        
        if status and status != "All":
            if status == "Select":
                query = query.filter(Interview.overall_score > 6)
            elif status == "Consider":
                query = query.filter(Interview.overall_score > 4, Interview.overall_score <= 6)
            elif status == "Reject":
                query = query.filter(Interview.overall_score <= 4)
            elif status == "Not Completed":
                query = query.filter(or_(Interview.id == None, Interview.status != "completed"))
            else:
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
                query = query.filter(Application.resume_extraction.has(ResumeExtraction.experience_level.ilike(exp_val)))

        if skill and skill != "All":
            from app.domain.models import ResumeExtraction
            query = query.filter(Application.resume_extraction.has(ResumeExtraction.extracted_skills.ilike(f"%{skill}%")))

        if search:
            term = f"%{search}%"
            query = query.filter(or_(
                Application.candidate_name.ilike(term),
                Application.candidate_email.ilike(term),
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

        total = query.count()
        applications = query.options(
            joinedload(Application.interview).joinedload(Interview.report),
            joinedload(Application.hiring_decision),
            joinedload(Application.hr),
            joinedload(Application.resume_extraction),
            joinedload(Application.job)
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
                                evaluation.setdefault("clarity", float(ans.clarity_score or base_overall))
                            elif q_type_lower != "aptitude":
                                evaluation.setdefault("technical_accuracy", float(ans.technical_score or ans.skill_relevance_score or base_overall))
                                evaluation.setdefault("completeness", float(ans.completeness_score or base_overall))
                                evaluation.setdefault("clarity", float(ans.clarity_score or base_overall))
                                evaluation.setdefault("depth", float(ans.depth_score or base_overall))
                                evaluation.setdefault("practicality", float(ans.practicality_score or base_overall))

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
                all_q = question_evaluations + aptitude_evals
                tech_s = [q.get("score", 0) for q in all_q if q.get("question_type") == "technical"]
                beh_s = [q.get("score", 0) for q in all_q if q.get("question_type") == "behavioral"]
                apt_q = aptitude_evals
                
                tech_avg = sum(tech_s) / len(tech_s) if tech_s else 0
                beh_avg = sum(beh_s) / len(beh_s) if beh_s else 0
                apt_qty = len(apt_q)
                apt_correct = sum(1 for q in apt_q if q.get("correct"))

                apt_score = (apt_correct / apt_qty * 10) if apt_qty > 0 else 0

                # 4. Construct Final Response with Safe Timestamps
                created = None
                if report and hasattr(report, 'created_at') and report.created_at:
                    created = report.created_at
                elif interview and hasattr(interview, 'created_at') and interview.created_at:
                    created = interview.created_at
                else:
                    created = app.applied_at
                
                # Identification Fallbacks
                report_id = report.id if report else (f"skel_{interview.id}" if interview else f"app_{app.id}")
                interview_id = interview.id if interview else None
                test_id = interview.test_id if interview else None
                filename = f"report_{interview.id}.json" if interview else f"app_{app.id}.json"
                video_url = f"/api/interviews/{interview.id}/video-stream" if (interview and hasattr(interview, 'video_recording_path') and interview.video_recording_path) else None

                reports.append({
                    "id": report_id,
                    "interview_id": interview_id,
                    "filename": filename,
                    "test_id": test_id,
                    "timestamp": created.isoformat() if created else "",
                    "display_date": created.strftime("%Y-%m-%d %H:%M:%S") if created else "",
                    "display_date_short": created.strftime("%b %d, %Y") if created else "",
                    "status": app.status if app else (interview.status if interview else "unknown"),
                    "overall_score": float(report.overall_score if (report and report.overall_score is not None) else (interview.overall_score if (interview and interview.overall_score is not None) else 0)),
                    "final_score": float(report.combined_score if (report and report.combined_score is not None) else (interview.overall_score if (interview and interview.overall_score is not None) else 0)),
                    "technical_score": float(tech_avg if tech_s else (report.technical_skills_score if (report and report.technical_skills_score is not None) else 0)),
                    "behavioral_score": float(beh_avg if beh_s else (report.behavioral_score if (report and report.behavioral_score is not None) else 0)),
                    "aptitude_score": float(apt_score if apt_qty > 0 else (report.aptitude_score if (report and report.aptitude_score is not None) else 0)),
                    "total_questions_answered": len([e for e in question_evaluations if e.get("answer")]),
                    "aptitude_questions_answered": apt_qty,
                    "question_evaluations": question_evaluations,
                    "aptitude_question_evaluations": aptitude_evals,
                    "candidate_profile": candidate_profile,
                    "recommendation": report.recommendation if report else "consider",
                    "video_url": video_url,
                    "assigned_hr_id": app.hr_id,
                    "assigned_hr_name": app.hr.full_name if (hasattr(app, 'hr') and app.hr) else "Unknown",
                    "is_owner": (app.hr_id == current_user.id) if (current_user and hasattr(current_user, 'id')) else False,
                    "termination_reason": getattr(report, 'termination_reason', None)
                })
            except Exception as e:
                # Log specific error and keep going
                logger.warning(f"[REPORTS][SKIPPED] Application record failed processing: {str(e)}")
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



        # Final sort - newest first by timestamp (avoiding mixed type ID comparison crash)
        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        logger.info(f"[REPORTS] Found {len(reports)} records for HR {current_user.id} (failed: {failed_count})")
        
        return {
            "reports": reports,
            "total": total,
            "count": len(reports),
            "failed": failed_count,
            "pages": (total + limit - 1) // limit if limit > 0 else 1
        }

    except Exception as e:
        import traceback
        logger.critical("CRITICAL ERROR in get_interview_reports:")
        logger.error(traceback.format_exc())
        return {
            "reports": [],
            "total": 0,
            "count": 0,
            "failed": 0,
            "pages": 0
        }

@router.get("/interviews")
def get_filtered_interviews(
    candidate_name: Optional[str] = None,
    candidate_email: Optional[str] = None,
    test_id: Optional[str] = None,
    role_applied: Optional[str] = None,
    search: Optional[str] = None,
    date: Optional[str] = None,
    status: Optional[str] = None,
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
    from sqlalchemy import or_
    
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

    # Apply global search if present
    if search:
        query = query.filter(or_(
            Application.candidate_name.ilike(f"%{search}%"),
            Application.candidate_email.ilike(f"%{search}%"),
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
        if status == "hired":
            query = query.filter(Application.status.in_(['hired', 'accepted', 'onboarded']))
        elif status == "completed":
            query = query.filter(or_(
                Interview.status == 'completed',
                Application.status == 'interview_completed'
            ))
        elif status == "rejected":
            query = query.filter(Application.status == 'rejected')
        elif status == "not_started":
            # Either interview explicitly not started, or application still in early stages
            query = query.filter(or_(
                Interview.status == 'not_started',
                Application.status.in_(['applied', 'screened']),
                Interview.id == None # No interview record yet
            ))
        elif status == "in_progress":
            query = query.filter(or_(
                Interview.status == 'in_progress',
                Application.status.in_(['aptitude_round', 'ai_interview', 'physical_interview'])
            ))
        else:
            # Fallback for any other specific status
            query = query.filter(or_(
                Interview.status == status,
                Application.status == status
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
    applications = query.order_by(Application.applied_at.desc()).offset(skip).limit(limit).all()

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

