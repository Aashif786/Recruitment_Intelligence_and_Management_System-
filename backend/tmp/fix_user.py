import sys
import os
sys.path.append(os.getcwd())

from app.infrastructure.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    from app.core.config import get_settings
    settings = get_settings()
    admin_email = (settings.super_admin_email or '').lower().strip()
    if admin_email:
        conn.execute(text("UPDATE users SET role = 'super_admin', approval_status = 'approved' WHERE email = :email"), {"email": admin_email})
        conn.commit()
        print(f"Promoted {admin_email} to super_admin")
    else:
        print("No super_admin_email configured in settings. Skipping promotion.")

    # Also backfill applications.hr_id if missing
    try:
        conn.execute(text("UPDATE applications SET hr_id = (SELECT hr_id FROM jobs WHERE jobs.id = applications.job_id) WHERE hr_id IS NULL"))
        conn.commit()
        print("Backfilled applications.hr_id")
    except:
        pass
