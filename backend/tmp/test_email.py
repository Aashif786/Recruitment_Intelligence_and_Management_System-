import asyncio
import sys
import os
sys.path.append(os.getcwd())

from app.services.email_service import send_approved_for_interview_email
from app.core.config import get_settings

async def test_email():
    try:
        settings = get_settings()
        print(f"Testing email sending to {settings.super_admin_email or settings.smtp_from or settings.smtp_user}")
        to_email = settings.super_admin_email or settings.smtp_user or ""
        print(f"SMTP Host: {settings.smtp_host}, User: {settings.smtp_user}")
        result = await send_approved_for_interview_email(to_email, "Software Engineer", "TEST-KEY-123")
        print("Result:", result)
    except Exception as e:
        print("Error sending test email:", e)

if __name__ == "__main__":
    asyncio.run(test_email())
