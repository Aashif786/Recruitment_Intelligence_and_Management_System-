import os
import sys
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.database import SessionLocal
from app.domain.models import InterviewAnswer, InterviewQuestion, Interview

def check_answers():
    db = SessionLocal()
    try:
        # Let's find recent interview answers that have a score of 4.0 or fallback_used = True
        answers = db.query(InterviewAnswer).filter(
            (InterviewAnswer.answer_score == 4.0) | (InterviewAnswer.fallback_used == True)
        ).order_by(InterviewAnswer.submitted_at.desc()).limit(10).all()
        
        print(f"Found {len(answers)} answers with score 4.0 or fallback_used=True:\n")
        for ans in answers:
            q = db.query(InterviewQuestion).filter(InterviewQuestion.id == ans.question_id).first()
            q_text = q.question_text if q else "Unknown question"
            q_type = q.question_type if q else "unknown"
            
            print(f"Answer ID: {ans.id} | Interview ID: {ans.interview_id}")
            print(f"Question Type: {q_type} | Question: {q_text}")
            print(f"Candidate Answer: '{ans.answer_text}'")
            print(f"Score: {ans.answer_score} | Skill Relevance: {ans.skill_relevance_score}")
            print(f"Fallback Used: {ans.fallback_used} | AI Used: {ans.ai_used}")
            print(f"Evaluated At: {ans.evaluated_at}")
            print(f"Evaluation JSON: {ans.answer_evaluation}")
            print(f"Reasoning: {ans.reasoning}")
            print("-" * 80)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_answers()
