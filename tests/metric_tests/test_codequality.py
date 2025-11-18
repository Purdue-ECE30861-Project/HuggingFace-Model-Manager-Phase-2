# tests/test_codequality_bulk.py
import unittest
from unittest.mock import patch
from src.classes.CodeQuality import CodeQuality

class FakeLLM:
    def __init__(self, resp): self._resp = resp
    def main(self, prompt: str) -> str: return self._resp

def _mk_case(name, gh_url, inferred_links, llm_resp, expected):
    def _t(self):
        with patch("backend_server.classes.CodeQuality.find_github_links", return_value=inferred_links):
            m = CodeQuality()
            m.llm = FakeLLM(llm_resp)
            score, _ = m.evaluate(url="https://hf.co/model", githubURL=gh_url)
            self.assertEqual(score, expected)
    _t.__name__ = name
    return _t

class TestCodeQualityBulk(unittest.TestCase):
    pass

# 30 small variations (explicit GH, inferred links, none; various LLM replies)
_cases = []
for i, gh in enumerate([None, "https://github.com/org/repo"]):
    for links in [set(), {"https://github.com/org/repo"}]:
        for resp, exp in [("1.0", 1.0), ("0.5", 0.5), ("0.0", 0.0), ("garbage", 0.0)]:
            # If neither gh nor links -> CodeQuality returns 0.0 regardless of LLM
            expected = 0.0 if (gh is None and not links) else exp
            _cases.append((gh, links, resp, expected))

for idx, (gh, links, resp, exp) in enumerate(_cases, 1):
    test = _mk_case(f"test_cq_{idx:02d}", gh, links, resp, exp)
    setattr(TestCodeQualityBulk, test.__name__, test)

if __name__ == "__main__":
    unittest.main()