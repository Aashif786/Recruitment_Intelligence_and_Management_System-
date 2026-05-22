import sys
import os
from pathlib import Path

# Add the current directory to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from app.infrastructure.database import SessionLocal
from app.domain.models import User
from app.core.auth import hash_password

def reset_user_password(email: str, new_password: str):
    email = email.lower().strip()
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"Error: User {email} not found in database.")
            return

        user.password_hash = hash_password(new_password)
        user.role = "super_admin"  # Elevate to super_admin just in case
        user.is_active = True
        user.is_verified = True
        user.approval_status = "approved"
        
        db.commit()
        print(f"Success: Password for {email} has been reset and account is now an active Super Admin.")
        print(f"Login with: {email} / {new_password}")
    except Exception as e:
        db.rollback()
        print(f"Error: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    from app.core.config import get_settings
    settings = get_settings()
    
    target_email = settings.super_admin_email or ""
    target_password = settings.super_admin_password or ""
    
    if len(sys.argv) > 1:
        target_email = sys.argv[1]
    if len(sys.argv) > 2:
        target_password = sys.argv[2]
        
    if not target_email or not target_password:
        print("Usage: python reset_admin.py <email> <password>")
        print("Or configure SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD in environment.")
        sys.exit(1)
        
    reset_user_password(target_email, target_password)
