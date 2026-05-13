
import pytest
from fastapi.testclient import TestClient

def test_regression_candidate_filtering(client: TestClient, hr_auth_headers, sample_application):
    # Ensure standard filtering still works after deterministic sorting update
    response = client.get("/api/onboarding/candidates", headers=hr_auth_headers)
    assert response.status_code == 200
    assert "items" in response.json()["data"]
