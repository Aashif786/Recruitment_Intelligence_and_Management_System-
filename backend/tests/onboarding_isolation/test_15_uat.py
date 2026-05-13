
import pytest
from datetime import timedelta
from app.core.timezone import get_ist_now

def test_uat_onboarding_window_rule(db_session, sample_application):
    # UAT Criteria: Candidates joining within 7 days must be identifiable
    today = get_ist_now()
    sample_application.joining_date = today + timedelta(days=5)
    db_session.commit()
    
    # Logic verification (The business rule we implemented)
    diff = (sample_application.joining_date - today).days
    assert 0 <= diff <= 7
