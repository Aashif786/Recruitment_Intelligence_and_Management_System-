"""
API submit_answer: Redis-backed (or local fallback) request-id idempotency.
Replaces the deprecated WebSocket gateway idempotency tests.
"""

import os
import datetime
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
import sqlalchemy
from sqlalchemy.pool import StaticPool

# Patch create_engine for SQLite in tests
original_create_engine = sqlalchemy.create_engine

def mocked_create_engine(*args, **kwargs):
    if args and args[0].startswith("sqlite"):
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_recycle", None)
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = kwargs.get("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return original_create_engine(*args, **kwargs)

sqlalchemy.create_engine = mocked_create_engine

# Set test environment before any app/FastAPI imports
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-for-idempotency-tests"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["BACKEND_START_MODE"] = "script"

from app.main import app
from app.infrastructure.database import Base, engine, get_db, SessionLocal
from app.domain.models import Interview, InterviewQuestion, InterviewAnswer, Application, Job, User
from app.core.auth import get_current_interview
from app.core.timezone import get_ist_now


class TestApiSubmitIdempotency(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        self.db = SessionLocal()
        # Clean up database tables for each test
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())
        self.db.commit()

        # Create test HR user
        self.hr = User(
            email="hr@testcompany.com",
            password_hash="fakehash",
            full_name="HR Manager",
            role="hr",
            is_active=True,
            is_verified=True,
            approval_status="approved",
        )
        self.db.add(self.hr)
        self.db.commit()

        # Create test job
        self.job = Job(
            title="Software Engineer",
            description="Build cool things.",
            experience_level="mid",
            location="Remote",
            status="open",
            hr_id=self.hr.id,
            duration_minutes=60,
            interview_mode="manual",
        )
        self.db.add(self.job)
        self.db.commit()

        # Create test application
        self.app_record = Application(
            job_id=self.job.id,
            hr_id=self.hr.id,
            candidate_name="Jane Applicant",
            candidate_email="jane@example.com",
            status="applied",
        )
        self.db.add(self.app_record)
        self.db.commit()

        # Create test interview
        self.interview = Interview(
            application_id=self.app_record.id,
            status="in_progress",
            total_questions=10,
            questions_asked=0,
            interview_stage="first_level",
            duration_minutes=60,
            started_at=get_ist_now()
        )
        self.db.add(self.interview)
        self.db.commit()

        # Create test interview question
        self.question = InterviewQuestion(
            interview_id=self.interview.id,
            question_number=1,
            question_text="What is mutability in Python?",
            question_type="technical",
        )
        self.db.add(self.question)
        self.db.commit()

        # Set up dependency override for get_db
        def _override_get_db():
            try:
                yield self.db
            finally:
                pass

        # Set up dependency override for get_current_interview
        def _override_get_current_interview():
            return self.interview

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_interview] = _override_get_current_interview
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        # Clean local idempotency seen cache
        from app.core.idempotency import _SEEN
        _SEEN.clear()

    def test_duplicate_request_returns_idempotent_replay(self):
        with patch("app.api.interviews.evaluate_answer_task", new_callable=AsyncMock) as mock_eval_task:
            headers = {"X-Request-ID": "req-replay-1"}
            data = {
                "question_id": self.question.id,
                "answer_text": "This is a valid answer explaining mutability in Python: lists can be changed in place, but tuples cannot."
            }

            # First submit
            response1 = self.client.post(
                f"/api/interviews/{self.interview.id}/submit-answer",
                headers=headers,
                json=data
            )
            self.assertEqual(response1.status_code, 200)
            json_res1 = response1.json()
            self.assertTrue(json_res1["success"])
            self.assertFalse(json_res1["idempotent_replay"])

            # Second submit (replay)
            response2 = self.client.post(
                f"/api/interviews/{self.interview.id}/submit-answer",
                headers=headers,
                json=data
            )
            self.assertEqual(response2.status_code, 200)
            json_res2 = response2.json()
            self.assertTrue(json_res2["success"])
            self.assertTrue(json_res2["idempotent_replay"])
            self.assertEqual(json_res1["answer_id"], json_res2["answer_id"])

    def test_duplicate_request_without_saved_answer_returns_409(self):
        with patch("app.api.interviews.is_duplicate_request", return_value=True):
            headers = {"X-Request-ID": "req-duplicate-409"}
            data = {
                "question_id": self.question.id,
                "answer_text": "Some answer text."
            }
            response = self.client.post(
                f"/api/interviews/{self.interview.id}/submit-answer",
                headers=headers,
                json=data
            )
            self.assertEqual(response.status_code, 409)
            resp_json = response.json()
            error_message = resp_json.get("error") or resp_json.get("detail") or resp_json.get("data", {}).get("detail")
            self.assertIsNotNone(error_message, f"Response JSON did not contain error details: {resp_json}")
            self.assertIn("Duplicate submit request detected", error_message)


if __name__ == "__main__":
    unittest.main()
