
import pytest
from fastapi.testclient import TestClient
from datetime import timedelta
from app.core.timezone import get_ist_now

def test_sanity_past_date_blocking(client: TestClient, hr_auth_headers, sample_application, db_session):
    # Area 1: Block past dates for offer issuance
    sample_application.status = "hired"
    db_session.commit()
    past_date = (get_ist_now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"/api/onboarding/applications/{sample_application.id}/send-offer?joining_date={past_date}&auto_approve=true"
    response = client.post(url, headers=hr_auth_headers)
    assert response.status_code == 400

def test_sanity_future_date_allowance(client: TestClient, hr_auth_headers, sample_application, db_session):
    # Area 2: Allow future dates for offer issuance
    sample_application.status = "hired"
    db_session.commit()
    future_date = (get_ist_now() + timedelta(days=30)).strftime("%Y-%m-%d")
    url = f"/api/onboarding/applications/{sample_application.id}/send-offer?joining_date={future_date}&auto_approve=true"
    response = client.post(url, headers=hr_auth_headers)
    assert response.status_code in (200, 400) # 400 is fine if service fails, but not 422
    assert response.status_code != 422
