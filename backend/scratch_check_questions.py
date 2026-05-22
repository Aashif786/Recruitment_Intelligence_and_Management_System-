import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.database import SessionLocal
from app.domain.models import Interview, InterviewQuestion, Application, Job

def check_interviews():
    db = SessionLocal()
    try:
        interviews = db.query(Interview).order_by(Interview.created_at.desc()).limit(5).all()
        print(f"Found {len(interviews)} recent interviews:\n")
        for iv in interviews:
            app = db.query(Application).filter(Application.id == iv.application_id).first()
            job = db.query(Job).filter(Job.id == app.job_id).first() if app else None
            
            print(f"Interview ID: {iv.id} | Status: {iv.status}")
            print(f"Candidate: {app.candidate_name if app else 'N/A'} ({app.candidate_email if app else 'N/A'})")
            print(f"Job: {job.title if job else 'N/A'} | Locked Skill: {iv.locked_skill}")
            
            # Fetch questions
            questions = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id == iv.id
            ).order_by(InterviewQuestion.question_number).all()
            
            print(f"Total Questions: {len(questions)}")
            for q in questions:
                print(f"  Q{q.question_number} ({q.question_type}): '{q.question_text}'")
            print("=" * 80)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_interviews()
