import sys
import os
sys.path.append(os.getcwd())

from app.infrastructure.database import SessionLocal
from app.domain.models import User
from app.core.auth import hash_password

db = SessionLocal()
try:
    email = "hr_automated_test@example.com"
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            full_name="Automated HR Test",
            password_hash=hash_password("password123"),
            role="hr",
            is_active=True,
            is_verified=True,
            approval_status="approved"
        )
        db.add(user)
        print(f"Created user: {email}")
    else:
        user.password_hash = hash_password("password123")
        user.role = "hr"
        user.is_active = True
        user.is_verified = True
        user.approval_status = "approved"
        print(f"Updated user: {email}")
    db.commit()
finally:
    db.close()
