# tests/test_llm.py
import os
import unittest
from unittest.mock import patch, MagicMock

import requests
from src.backend_server.utils.llm_api import LLMAccessor


class MakePromptTests(unittest.TestCase):
    def setUp(self):
        self.api = LLMAccessor()
        self.fake_token = "FAKE_TOKEN"
        self.role = "user"
        self.content = "Hello, world!"

    @patch("requests.post")
    def test_make_prompt_success(self, mpost):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"reply":"hi"}'
        mpost.return_value = mock_resp

        out = self.api.make_prompt(self.fake_token, self.role, self.content)
        self.assertEqual(out, '{"reply":"hi"}')

        called_url = mpost.call_args[0][0]
        called_headers = mpost.call_args[1]["headers"]
        called_json = mpost.call_args[1]["json"]

        self.assertEqual(called_url, "https://genai.rcac.purdue.edu/api/chat/completions")
        self.assertEqual(called_headers["Authorization"], f"Bearer {self.fake_token}")
        self.assertEqual(called_headers["Content-Type"], "application/json")
        self.assertEqual(called_json["messages"][0]["role"], self.role)
        self.assertEqual(called_json["messages"][0]["content"], self.content)

    @patch("requests.post")
    def test_make_prompt_failure_raises(self, mpost):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "server error"
        mpost.return_value = mock_resp

        with self.assertRaises(Exception) as ctx:
            self.api.make_prompt(self.fake_token, self.role, self.content)

        self.assertIn("Error: 500", str(ctx.exception))


class MainTests(unittest.TestCase):
    def setUp(self):
        self.api = LLMAccessor()

    @patch.dict(os.environ, {"GEN_AI_STUDIO_API_KEY": "ENV_TOKEN"}, clear=True)
    @patch("requests.post")
    def test_main_uses_env_key_and_calls_api(self, mpost):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mpost.return_value = mock_resp

        out = self.api.main("hello")
        self.assertEqual(out, "OK")

        # ensure called with our env token
        called_headers = mpost.call_args[1]["headers"]
        self.assertEqual(called_headers.get("Authorization"), "Bearer ENV_TOKEN")

    @patch("backend_server.utils.llm_api.load_dotenv", return_value=False)  # prevent loading local .env
    @patch.dict(os.environ, {}, clear=True)                      # ensure env is empty
    @patch("requests.post")                                      # guard against any accidental network call
    def test_main_raises_if_no_key(self, mpost, _noop_loadenv):
        with self.assertRaises(RuntimeError) as ctx:
            self.api.main("hello")

        # Your implementation raises this specific message:
        self.assertIn("Missing GENAI_STUDIO_TOKEN", str(ctx.exception))

        # Make sure we did NOT hit the network
        mpost.assert_not_called()


if __name__ == "__main__":
    unittest.main()
