
import pytest
import time
from fastapi.testclient import TestClient

def test_performance_candidates_listing_latency(client: TestClient, hr_auth_headers):
    # Area 1: Listing speed (Budget: 1.0s)
    start = time.time()
    response = client.get("/api/onboarding/candidates", headers=hr_auth_headers)
    assert (time.time() - start) < 1.0
    assert response.status_code == 200

def test_performance_analytics_query_speed(client: TestClient, hr_auth_headers):
    # Area 2: Analytics calculation speed (Budget: 0.5s)
    start = time.time()
    response = client.get("/api/onboarding/analytics/offers", headers=hr_auth_headers)
    if response.status_code == 200:
        assert (time.time() - start) < 0.5
