import sys
import os
sys.path.append(os.getcwd())

from app.infrastructure.database import SessionLocal
from app.domain.models import User

db = SessionLocal()
try:
    users = db.query(User).all()
    for u in users:
        print(f"Email: {u.email}, Role: {u.role}, Status: {u.approval_status}, Active: {u.is_active}")
finally:
    db.close()
