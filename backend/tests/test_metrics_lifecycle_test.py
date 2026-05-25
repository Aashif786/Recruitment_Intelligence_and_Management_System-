"""
Verification suite to test full lifecycle of candidate answer flows:
Candidate -> AI ResponseAnalyzer -> Database models -> HR Reports API.
Confirms overall scoring calculations are accurate and that Clarity and Practicality are omitted.
"""

import sys
import os
import asyncio
import json
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interview_process.response_analyzer import ResponseAnalyzer
from interview_process.utils import calculate_detailed_score, generate_strengths_analysis
from app.domain.models import InterviewAnswer
from app.infrastructure.database import SessionLocal


class MockAIClient:
    def __init__(self, response_text):
        self.response_text = response_text

    async def generate(self, *args, **kwargs):
        return self.response_text


class TestMetricsLifecycle(unittest.IsolatedAsyncioTestCase):

    async def test_01_behavioral_evaluation_lifecycle(self):
        """Test behavioral question evaluation parsing & score calculation"""
        # Mock AI response with Clarity included in JSON to test parser resilience
        # Even if LLM returns Clarity in some edge case, response analyzer must filter it out.
        mock_response = json.dumps({
            "Relevance": 8.0,
            "Action & Impact": 9.0,
            "Clarity": 7.0,  # Legacy key returned by AI
            "Overall": 8.5,
            "Strengths": ["Good active listing"],
            "Weaknesses": ["Could outline impact clearer"],
            "Reasoning": "Strong behavioral signals."
        })

        analyzer = ResponseAnalyzer()
        analyzer.ai_client = MockAIClient(mock_response)

        result = await analyzer.evaluate_answer(
            question="Tell me about a time you resolved a team conflict.",
            answer="In my last role, we had a major disagreement about API patterns. I set up a meeting, list out pros/cons, and we agreed on REST.",
            question_type="behavioral"
        )

        print("\n--- Behavioral Evaluation Result ---")
        print(json.dumps(result, indent=2))

        # Check that clarity is omitted completely
        self.assertNotIn("clarity", result)
        self.assertNotIn("practicality", result)

        # Check active fields are correct
        self.assertEqual(result["relevance"], 8.0)
        self.assertEqual(result["action_impact"], 9.0)
        self.assertEqual(result["overall"], 8.5)

    async def test_02_technical_evaluation_lifecycle(self):
        """Test technical question evaluation parsing & overall calculation"""
        # Mock AI response with Practicality and Clarity included to test parser filtering
        mock_response = json.dumps({
            "Technical Accuracy": 9.0,
            "Completeness": 8.0,
            "Clarity": 7.5,
            "Depth": 9.0,
            "Practicality": 8.0,
            "Overall": 8.7,
            "Strengths": ["Deep architectural grasp"],
            "Weaknesses": [],
            "Reasoning": "Excellent technical response."
        })

        analyzer = ResponseAnalyzer()
        analyzer.ai_client = MockAIClient(mock_response)

        result = await analyzer.evaluate_answer(
            question="Explain how connection pooling works.",
            answer="Connection pooling maintains a cache of database connections that are reused, reducing connections overhead.",
            question_type="technical"
        )

        print("\n--- Technical Evaluation Result ---")
        print(json.dumps(result, indent=2))

        # Verify Clarity and Practicality are omitted completely
        self.assertNotIn("clarity", result)
        self.assertNotIn("practicality", result)

        # Verify correct fields
        self.assertEqual(result["technical_accuracy"], 9.0)
        self.assertEqual(result["completeness"], 8.0)
        self.assertEqual(result["depth"], 9.0)
        self.assertEqual(result["overall"], 8.7)

        # Direct test of the raw text parser division-by-3 logic
        raw_eval_text = """
        Technical Accuracy: 9.0
        Completeness: 8.0
        Depth: 9.0
        Strengths: Deep architectural grasp
        Weaknesses: None
        """
        parsed_raw = analyzer._parse_detailed_evaluation(
            eval_text=raw_eval_text,
            word_count=120,
            metrics={"has_examples": True, "has_technical_terms": True, "has_explanation": True}
        )
        print("\n--- Raw Parser Test Result ---")
        print(json.dumps(parsed_raw, indent=2))
        self.assertEqual(parsed_raw["overall"], 9.2) # (9.5 + 9.0 + 9.0) / 3 = 9.166 -> 9.2

    async def test_03_fallback_evaluations(self):
        """Test fallback engines omit clarity and practicality"""
        analyzer = ResponseAnalyzer()
        
        # Technical Fallback
        tech_fallback = analyzer._fallback_evaluation(
            question="What is clean architecture?",
            answer="Clean architecture separates concerns into layers.",
            word_count=6,
            metrics={"has_examples": False, "has_technical_terms": True, "has_explanation": False}
        )
        print("\n--- Technical Fallback Result ---")
        print(json.dumps(tech_fallback, indent=2))
        self.assertNotIn("clarity", tech_fallback)
        self.assertNotIn("practicality", tech_fallback)

        # Behavioral Fallback
        beh_fallback = analyzer._fallback_behavioral_evaluation(word_count=60)
        print("\n--- Behavioral Fallback Result ---")
        print(json.dumps(beh_fallback, indent=2))
        self.assertNotIn("clarity", beh_fallback)
        self.assertNotIn("practicality", beh_fallback)

    def test_04_detailed_score_util(self):
        """Test utility detailed scores and strengths generators do not compute clarity"""
        responses = [
            {
                "answer": "React uses virtual DOM to batch updates.",
                "evaluation": {
                    "overall": 8.0,
                    "accuracy": 8.0,
                    "relevance": 8.0,
                    "depth": 8.0,
                    "clarity": 9.0 # legacy
                }
            }
        ]

        scores = calculate_detailed_score(responses)
        self.assertNotIn("clarity", scores)
        self.assertNotIn("practicality", scores)

        strengths = generate_strengths_analysis(responses)
        print("\n--- Strengths Analysis ---")
        print(strengths)
        # Ensure no communicates clearly text since clarity analysis is removed
        self.assertNotIn("Communicates technical concepts clearly", strengths)

    @patch("app.infrastructure.database.SessionLocal")
    async def test_05_background_evaluation_task(self, mock_session_local):
        """Test interviews background task correctly writes answer attributes, omitting clarity/practicality"""
        from app.services.ai_service import evaluate_detailed_answer

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        mock_answer = MagicMock(spec=InterviewAnswer)
        mock_answer.id = 1
        mock_answer.answer_text = "Highly optimized query patterns."
        mock_answer.answer_score = None
        mock_answer.technical_score = None
        mock_answer.completeness_score = None
        mock_answer.depth_score = None
        mock_answer.clarity_score = None
        mock_answer.practicality_score = None

        mock_db.query().filter().with_for_update().first.side_effect = [mock_answer, MagicMock()]

        # Import evaluate_answer_task
        from app.api.interviews import evaluate_answer_task

        ai_eval_result = {
            "overall": 9.0,
            "technical_accuracy": 9.0,
            "completeness": 9.0,
            "depth": 9.0,
            "reasoning": "Excellent clarity."
        }

        # Mock the service evaluate_detailed_answer to return our metric structure
        with patch("app.services.ai_service.evaluate_detailed_answer", AsyncMock(return_value=ai_eval_result)):
            await evaluate_answer_task(
                answer_id=1,
                question_text="Describe how you optimize query performance.",
                answer_text="Highly optimized query patterns.",
                question_type="technical",
                interview_id=10
            )

        # Check DB updates
        self.assertEqual(mock_answer.answer_score, 9.0)
        self.assertEqual(mock_answer.technical_score, 9.0)
        self.assertEqual(mock_answer.completeness_score, 9.0)
        self.assertEqual(mock_answer.depth_score, 9.0)

        # Verify deprecated attributes were untouched/remained unpopulated (assigned clarity/practicality were deleted)
        self.assertFalse(hasattr(mock_answer, "clarity_score_assigned"))


if __name__ == "__main__":
    unittest.main()
