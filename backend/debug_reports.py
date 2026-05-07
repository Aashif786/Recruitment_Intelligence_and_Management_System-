from app.infrastructure.database import SessionLocal
from app.api.analytics import get_interview_reports
from app.domain.models import User
import json

def test():
    db = SessionLocal()
    user = db.query(User).filter(User.id == 26).first()
    if not user:
        print("User 26 not found")
        return
    
    try:
        reports = get_interview_reports(db, user)
        print(f"Total Reports Found: {len(reports)}")
        if reports:
            print("First Report Preview:")
            print(json.dumps(reports[0], indent=2, default=str)[:500])
    except Exception as e:
        print(f"Error calling get_interview_reports: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
