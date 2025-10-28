import unittest
from unittest.mock import patch
import json

from src.classes.License import License

# Minimal fake HF client that mirrors hfAPI().get_info(url, printCLI=False) -> JSON string
class FakeHF:
    def __init__(self, payload): self.payload = payload
    def get_info(self, url, printCLI=False): return self.payload

class FakeLLM:
    def __init__(self, text): self.text = text
    def main(self, prompt: str) -> str: return self.text


class TestLicense(unittest.TestCase):
    @patch("src.classes.License.hfAPI")
    def test_permissive_license_via_hf_metadata(self, HF):
        """
        Drive the 'read from model card' path — no LLM needed.
        """
        # Model card data with a permissive license (e.g., MIT)
        HF.return_value = FakeHF({
            "data": {
                "cardData": {"license": "mit"}
            }
        })
        m = License()
        # Pass a URL-looking string (the class expects a model URL in this path)
        score, latency_ms = m.evaluate("https://huggingface.co/org/model")
        self.assertTrue(0.0 <= score <= 1.0)
        # permissive licenses should score high; assert a reasonably high bound
        self.assertGreaterEqual(score, 0.8)
        self.assertIsInstance(latency_ms, int)
        self.assertGreaterEqual(latency_ms, 0)

    @patch("src.classes.License.hfAPI")
    def test_llm_fallback_when_no_metadata(self, HF):
        """
        When no license info is available in HF metadata, fall back to LLM.
        """
        HF.return_value = FakeHF({"data": {}})  # no cardData -> triggers LLM
        m = License()
        m.llm = FakeLLM('{"license_score": 0.3}')
        score, latency_ms = m.evaluate("https://huggingface.co/org/model-without-card")
        self.assertTrue(0.0 <= score <= 1.0)
        # We asked LLM for 0.3; the implementation clamps, so 0.3 should be respected.
        self.assertAlmostEqual(score, 0.3, places=3)
        self.assertIsInstance(latency_ms, int)
        self.assertGreaterEqual(latency_ms, 0)


if __name__ == "__main__":
    unittest.main()