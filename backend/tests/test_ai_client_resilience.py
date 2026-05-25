"""
Scaffold tests for Groq key resolution and AI_DISABLED-style guards.
Does not call the real Groq API; prompts and scoring remain untested here by design.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.ai_client import AIClient, is_ai_unavailable_response


class TestIsAiUnavailableResponse(unittest.TestCase):
    def test_none_empty_and_disabled_marker(self):
        self.assertTrue(is_ai_unavailable_response(None))
        self.assertTrue(is_ai_unavailable_response(""))
        self.assertTrue(is_ai_unavailable_response("   "))
        self.assertTrue(is_ai_unavailable_response("AI_DISABLED"))

    def test_usable_model_text(self):
        self.assertFalse(is_ai_unavailable_response('{"name": "x"}'))
        self.assertFalse(is_ai_unavailable_response("Some narrative answer."))


class TestGroqKeyResolution(unittest.TestCase):
    @patch("app.services.ai_client.AsyncGroq")
    @patch("app.core.config.get_settings")
    def test_prefers_first_key_from_settings(self, mock_get_settings, _mock_async_groq):
        settings = MagicMock()
        settings.groq_keys = ["primary-from-settings"]
        mock_get_settings.return_value = settings

        client = AIClient()
        self.assertEqual(client.api_key, "primary-from-settings")
        self.assertFalse(client.disabled)

    @patch("app.services.ai_client.AsyncGroq")
    @patch("app.core.config.get_settings")
    def test_falls_back_to_process_env_when_settings_empty(self, mock_get_settings, _mock_async_groq):
        settings = MagicMock()
        settings.groq_keys = []
        mock_get_settings.return_value = settings

        with patch.dict(os.environ, {"GROQ_API_KEY": "fallback-env-key"}, clear=False):
            client = AIClient()
        self.assertEqual(client.api_key, "fallback-env-key")
        self.assertFalse(client.disabled)


if __name__ == "__main__":
    unittest.main()
