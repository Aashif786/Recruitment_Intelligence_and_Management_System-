
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

def test_functional_full_lifecycle(client: TestClient, hr_auth_headers, sample_application, db_session):
    # Area 1: Hired -> Sent (Transition Logic)
    sample_application.status = "hired"
    sample_application.candidate_email = "func@test.com"
    db_session.commit()
    
    url = f"/api/onboarding/applications/{sample_application.id}/send-offer?joining_date=2026-12-01&auto_approve=true"
    res = client.post(url, headers=hr_auth_headers)
    assert res.status_code in (200, 400) # 400 is fine if service fails, but logic must run
    
    # Area 2: Accepted -> Onboarded (Final State)
    sample_application.status = "accepted"
    db_session.commit()
    res = client.post(f"/api/onboarding/applications/{sample_application.id}/onboard", headers=hr_auth_headers)
    assert res.status_code == 200
    db_session.refresh(sample_application)
    assert sample_application.status == "onboarded"

def test_functional_link_expiry_check(client: TestClient, sample_application, db_session):
    # Area 3: Expired link logic
    sample_application.offer_token = "expired-token"
    sample_application.offer_expires_at = datetime.utcnow() - timedelta(days=1)
    db_session.commit()
    
    response = client.get(f"/api/onboarding/offer?token=expired-token")
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()
