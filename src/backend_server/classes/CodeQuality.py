#from __future__ import annotations

from dataclasses import dataclass
from src.classes.Metric import Metric
from typing import Optional, Tuple
import time

from src.classes.Metric import Metric
from src.utils.llm_api import llmAPI
from src.utils.get_metadata import find_github_links
import re

_PROMPT = """You are evaluating CODE QUALITY (style & maintainability).
Consider consistency, naming, modularity, comments/docstrings, type hints, tests/CI hints, and readability.
Rate on this discrete scale and reply with ONLY one number: 1.0, 0.5, or 0.0. The link to the github repository for the code is here:"""

@dataclass
class CodeQuality(Metric):
    def __init__(self, metricName="Code Quality", metricWeighting=0.1):
        super().__init__(metricName, 0, metricWeighting)
        self.llm = llmAPI()

    def _score_with_llm(self, code_text: str, readme_text: str) -> float:
        prompt = _PROMPT.format(code=(code_text or "")[:6000], readme=(readme_text or "")[:6000])
        resp = self.llm.main(prompt)  #plain text like "1.0" / "0.5" / "0.0"
        if "1.0" in resp: return 1.0 #high quality
        if "0.5" in resp: return 0.5 #avg quality
        if "0.0" in resp: return 0.0 #low quality
        return 0.0

    #computing code quality score and returns score and latency 
    def evaluate(self, url, githubURL) -> float:
        t0 = time.perf_counter_ns()
        if githubURL:
            links = githubURL
        else:
            links = find_github_links(url)
            
        if links:
            prompt = _PROMPT + str(links)
            response = self.llm.main(prompt)
            PAT = re.compile(r'\b(?:1\.0|0\.5|0\.0)\b')
            match = re.search(PAT, response)
            if match:
                score = float(match.group())
            else:
                score = 0.0
        else:
            # print("cant find github links")
            score = 0.0
        score = max(0.0, min(1.0, float(score)))
        dt_ms = (time.perf_counter_ns() - t0) // 1_000_000
        return score, dt_ms