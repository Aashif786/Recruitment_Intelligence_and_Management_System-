import sys
import os
import uuid
sys.path.append(os.getcwd())

from app.infrastructure.database import SessionLocal
from app.domain.models import User, Job, Application

db = SessionLocal()
try:
    hr_email = "hr_automated_test@example.com"
    hr_user = db.query(User).filter(User.email == hr_email).first()
    if not hr_user:
        print(f"HR user {hr_email} not found!")
        sys.exit(1)

    # Check if job exists
    job = db.query(Job).filter(Job.hr_id == hr_user.id).first()
    if not job:
        job = Job(
            job_id="TEST-" + str(uuid.uuid4())[:8],
            interview_token=str(uuid.uuid4())[:50],
            title="Software Engineer (Automated Test)",
            description="Test Job Description",
            experience_level="Mid-Level",
            location="Remote",
            hr_id=hr_user.id,
            status="open",
            domain="Engineering",
            mode_of_work="Remote",
            job_type="Full-Time"
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        print(f"Created job: {job.title}")
    else:
        print(f"Using existing job: {job.title}")

    # Add some applications
    statuses = ["applied", "screened", "interview_scheduled", "interview_completed"]
    for i, status in enumerate(statuses):
        email = f"candidate_{i}@example.com"
        app = db.query(Application).filter(Application.candidate_email == email, Application.job_id == job.id).first()
        if not app:
            app = Application(
                job_id=job.id,
                candidate_name=f"Candidate {i}",
                candidate_email=email,
                status=status,
                hr_id=hr_user.id,
                resume_status="parsed"
            )
            db.add(app)
            print(f"Created application for {email} with status {status}")
    db.commit()
    print("Seeding completed successfully.")
finally:
    db.close()
