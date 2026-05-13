
import pytest
from fastapi.testclient import TestClient

def test_system_audit_trail(client: TestClient, hr_auth_headers, sample_application, db_session):
    # Test system integration with AuditLog
    url = f"/api/onboarding/applications/{sample_application.id}/onboard"
    sample_application.status = "accepted"
    db_session.commit()
    
    client.post(url, headers=hr_auth_headers)
    
    from app.domain.models import AuditLog
    log = db_session.query(AuditLog).filter(AuditLog.resource_id == sample_application.id).first()
    assert log is not None
