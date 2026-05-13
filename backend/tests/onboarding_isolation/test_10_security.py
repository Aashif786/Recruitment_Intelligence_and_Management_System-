
import pytest
from fastapi.testclient import TestClient
from app.domain.models import User, Application
from app.core.auth import create_access_token

def test_security_hr_isolation(client: TestClient, db_session, sample_application):
    # Area 1: Cross-HR access prevention
    hr2 = User(email="hr2_sec@test.com", password_hash="...", full_name="HR Two", role="hr", approval_status="approved", is_active=True)
    db_session.add(hr2)
    db_session.commit()
    token2 = create_access_token({"sub": str(hr2.id), "role": "hr"})
    
    url = f"/api/onboarding/applications/{sample_application.id}/onboard"
    response = client.post(url, headers={"Authorization": f"Bearer {token2}"})
    assert response.status_code == 403

def test_security_candidate_role_restriction(client: TestClient, db_session):
    # Area 2: Candidate role cannot access HR endpoints
    cand = User(email="cand_sec@test.com", password_hash="...", full_name="Cand", role="candidate", is_active=True)
    db_session.add(cand)
    db_session.commit()
    token = create_access_token({"sub": str(cand.id), "role": "candidate"})
    
    response = client.get("/api/onboarding/candidates", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

def test_security_unauthenticated_access(client: TestClient):
    # Area 3: No token access prevention
    response = client.get("/api/onboarding/candidates")
    assert response.status_code == 401

def test_security_token_tampering(client: TestClient):
    # Area 4: Invalid/Fake token rejection
    response = client.get("/api/onboarding/candidates", headers={"Authorization": "Bearer fake-token"})
    assert response.status_code == 401
