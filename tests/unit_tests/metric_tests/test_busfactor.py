# tests/test_busfactor.py
import unittest
from unittest.mock import patch
from src.backend_server.classes.bus_factor import BusFactor

class FakeLLM:
    def __init__(self, text="0.5"):
        self._text = text
    def main(self, prompt: str) -> str:
        return self._text

class TestBusFactor(unittest.TestCase):

    @patch("backend_server.classes.BusFactor.find_github_links", return_value=[])
    @patch("backend_server.classes.BusFactor.LLMAccessor")
    def test_llm_fallback_parses_score(self, LLM, _find):
        """
        No GH link found -> fallback to LLM. Patch LLMAccessor() so it returns '0.5'.
        """
        LLM.return_value = FakeLLM("0.5")

        m = BusFactor()
        m.setNumContributors(url="https://huggingface.co/model/x", githubURL=None)

        self.assertEqual(m.metricScore, 0.5)
        self.assertIsInstance(m.metricLatency, int)
        self.assertGreaterEqual(m.metricLatency, 0)

    @patch("backend_server.classes.BusFactor.get_collaborators_github",
           return_value=(42.0, 500.0, {"a","b","c","d","e"}))
    @patch("backend_server.classes.BusFactor.LLMAccessor")  # guard in case code falls back
    def test_metadata_path_with_explicit_github(self, LLM, _get):
        """
        Providing githubURL should directly use get_collaborators_github().
        Still patch LLMAccessor in case implementation unexpectedly falls back.
        """
        LLM.return_value = FakeLLM("0.0")  # not expected to be used

        m = BusFactor()
        m.setNumContributors(url="ignored", githubURL="https://github.com/org/repo")

        self.assertTrue(0.0 <= m.metricScore <= 1.0)
        self.assertIsInstance(m.metricLatency, int)

    @patch("backend_server.classes.BusFactor.find_github_links",
           return_value=["https://github.com/org/one"])  # LIST, not set
    @patch("backend_server.classes.BusFactor.get_collaborators_github",
           return_value=(0.0, 1.0, {"solo"}))
    @patch("backend_server.classes.BusFactor.LLMAccessor")  # guard against unexpected fallback
    def test_infer_link_then_metadata(self, LLM, _get, _find):
        """
        No explicit githubURL → infer via find_github_links() then call get_collaborators_github().
        """
        LLM.return_value = FakeLLM("0.0")  # not expected to be used

        m = BusFactor()
        m.setNumContributors(url="https://huggingface.co/model/y", githubURL=None)

        self.assertTrue(0.0 <= m.metricScore <= 1.0)
        self.assertIsInstance(m.metricLatency, int)

if __name__ == "__main__":
    unittest.main()