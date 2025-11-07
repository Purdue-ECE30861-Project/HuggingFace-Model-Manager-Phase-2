import unittest
from unittest.mock import patch
import json

from src.classes.PerformanceClaims import PerformanceClaims

# Fake HF client that returns the JSON structure evaluate() expects
class FakeHF:
    def __init__(self, payload): self.payload = payload
    def get_info(self, url, printCLI=False): return json.dumps(self.payload)

class LLMResp:
    def __init__(self, text): self.text = text
    def main(self, prompt: str) -> str: return self.text

class TestPerformanceClaims(unittest.TestCase):
    @patch("backend_server.classes.PerformanceClaims.hfAPI")
    def test_model_index_scoring(self, HF):
        # Minimal model-index with two metrics on one (task, dataset)
        modelinfo = {
            "data": {
                "model-index": [
                    {
                        "results": [
                            {
                                "task": {"type": "text-classification"},
                                "dataset": {"name": "imdb"},
                                "metrics": [
                                    {"type": "accuracy", "value": 0.90},
                                    {"type": "f1",       "value": 0.88},
                                ],
                            }
                        ]
                    }
                ]
            }
        }
        HF.return_value = FakeHF(modelinfo)
        m = PerformanceClaims()
        score, ms = m.evaluate("https://huggingface.co/org/model")
        self.assertGreaterEqual(score, 0.85)  # ~avg(0.90, 0.88)
        self.assertLessEqual(score, 1.0)
        self.assertIsInstance(ms, int)

    @patch("backend_server.classes.PerformanceClaims.hfAPI")
    def test_llm_fallback_0_5(self, HF):
        # No model-index -> triggers LLM fallback
        HF.return_value = FakeHF({"data": {}})
        m = PerformanceClaims(); m.llm = LLMResp("0.5")
        score, _ = m.evaluate("https://huggingface.co/model/noindex")
        self.assertEqual(score, 0.5)

    @patch("backend_server.classes.PerformanceClaims.hfAPI")
    def test_llm_fallback_default_0_0_on_garbage(self, HF):
        HF.return_value = FakeHF({"data": {}})
        m = PerformanceClaims(); m.llm = LLMResp("not a valid token")
        score, _ = m.evaluate("https://huggingface.co/model/noindex")
        self.assertEqual(score, 0.0)

if __name__ == "__main__":
    unittest.main()