
import pytest
from fastapi.testclient import TestClient

def test_api_candidates_list_schema(client: TestClient, hr_auth_headers):
    # Area 1: GET /candidates
    response = client.get("/api/onboarding/candidates", headers=hr_auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert "items" in data
    assert isinstance(data["items"], list)

def test_api_invalid_application_id(client: TestClient, hr_auth_headers):
    # Area 2: Error handling for invalid IDs
    response = client.post("/api/onboarding/applications/999999/onboard", headers=hr_auth_headers)
    assert response.status_code == 404

def test_api_analytics_schema(client: TestClient, hr_auth_headers):
    # Area 3: GET /analytics/offers
    response = client.get("/api/onboarding/analytics/offers", headers=hr_auth_headers)
    assert response.status_code in (200, 403) # 403 if only admin can access
    if response.status_code == 200:
        assert "upcoming_joinings" in response.json()["data"]
