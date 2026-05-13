
import pytest
from datetime import datetime, timezone

def test_compatibility_date_formats(db_session, sample_application):
    # Test compatibility with ISO date strings vs naive dates
    iso_date = "2026-12-01T00:00:00Z"
    jd = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
    sample_application.joining_date = jd
    db_session.commit()
    
    assert sample_application.joining_date.year == 2026
