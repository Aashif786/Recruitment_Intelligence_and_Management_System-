
import pytest
from fastapi.testclient import TestClient

def test_e2e_full_onboarding_journey(client: TestClient, hr_auth_headers, sample_application, db_session):
    # Stage 1: Hired -> Send Offer (Functional Check)
    sample_application.status = "hired"
    sample_application.candidate_email = "e2e@test.com"
    db_session.commit()
    
    url = f"/api/onboarding/applications/{sample_application.id}/send-offer?joining_date=2026-12-01&auto_approve=true"
    client.post(url, headers=hr_auth_headers)
    
    # Stage 2: Accepted (Simulated)
    sample_application.status = "accepted"
    db_session.commit()
    
    # Stage 3: Onboarded
    client.post(f"/api/onboarding/applications/{sample_application.id}/onboard", headers=hr_auth_headers)
    
    db_session.refresh(sample_application)
    assert sample_application.status == "onboarded"
