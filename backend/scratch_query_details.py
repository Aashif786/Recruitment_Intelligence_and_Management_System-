import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.database import SessionLocal
from app.domain.models import InterviewAnswer, InterviewQuestion, Interview

def check_interview_details(interview_id):
    db = SessionLocal()
    try:
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        if not interview:
            print(f"Interview {interview_id} not found.")
            return
            
        print(f"=== Interview ID: {interview.id} | Stage: {interview.interview_stage} | Status: {interview.status} ===")
        print(f"Candidate: {interview.application.candidate_name} | Job: {interview.application.job.title}")
        
        questions = db.query(InterviewQuestion).filter(InterviewQuestion.interview_id == interview_id).order_by(InterviewQuestion.question_number).all()
        print(f"\nQuestions in this interview ({len(questions)}):")
        for q in questions:
            ans = db.query(InterviewAnswer).filter(InterviewAnswer.question_id == q.id).first()
            print(f"Q{q.question_number} (ID: {q.id}) [{q.question_type}]: {q.question_text}")
            if ans:
                print(f"  -> Answer (ID: {ans.id}): '{ans.answer_text}'")
                print(f"  -> Score: {ans.answer_score} | Fallback Used: {ans.fallback_used} | AI Used: {ans.ai_used}")
            else:
                print("  -> (Not answered yet)")
            print("-" * 50)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_interview_details(318)
