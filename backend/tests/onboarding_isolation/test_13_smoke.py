
import pytest
from fastapi.testclient import TestClient

def test_smoke_onboarding_health(client: TestClient, hr_auth_headers):
    # Quick ping of the main dashboard data
    response = client.get("/api/onboarding/candidates", headers=hr_auth_headers)
    assert response.status_code == 200
