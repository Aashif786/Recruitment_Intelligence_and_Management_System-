import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.database import SessionLocal
from app.domain.models import Interview, InterviewAnswer, InterviewQuestion

def list_interviews():
    db = SessionLocal()
    try:
        interviews = db.query(Interview).order_by(Interview.id.desc()).limit(20).all()
        print(f"{'ID':<5} | {'Candidate':<20} | {'Job':<25} | {'Stage':<12} | {'Status':<12}")
        print("-" * 80)
        for iv in interviews:
            name = iv.application.candidate_name if iv.application else "N/A"
            job = iv.application.job.title if iv.application and iv.application.job else "N/A"
            print(f"{iv.id:<5} | {name:<20} | {job:<25} | {iv.interview_stage:<12} | {iv.status:<12}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    list_interviews()
