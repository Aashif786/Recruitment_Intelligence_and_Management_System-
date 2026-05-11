from fastapi import APIRouter
from fastapi.responses import RedirectResponse
import os

router = APIRouter()

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI")

@router.get("/linkedin/login")
def linkedin_login():
    linkedin_url = (
        f"https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=openid profile email w_member_social"
    )

    return RedirectResponse(linkedin_url)
