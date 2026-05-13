
import pytest
from app.api.onboarding import generate_employee_id
from app.domain.constants import CandidateState

def test_unit_employee_id_format(db_session):
    emp_id = generate_employee_id(db_session)
    assert emp_id.startswith("EMP-")
    assert len(emp_id) == 10

def test_unit_candidate_states():
    assert CandidateState.ONBOARDED.value == "onboarded"
    assert CandidateState.OFFER_SENT.value == "offer_sent"
