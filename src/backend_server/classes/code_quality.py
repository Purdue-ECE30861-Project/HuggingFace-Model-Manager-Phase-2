from __future__ import annotations

from dataclasses import dataclass
from ..utils.llm_api import llmAPI
from ..utils.get_metadata import find_github_links
import re
from pathlib import Path
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd

_PROMPT = """You are evaluating CODE QUALITY (style & maintainability).
Consider consistency, naming, modularity, comments/docstrings, type hints, tests/CI hints, and readability.
Rate on this discrete scale and reply with ONLY one number: 1.0, 0.5, or 0.0. The link to the github repository for the code is here:"""


class CodeQuality(MetricStd[float]):
    metric_name = "code_quality"

    def __init__(self, metric_weight=0.1):
        super().__init__(metric_weight)
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

        return score

    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, *args, **kwargs) -> float:
        #return self.evaluate(artifact_data.url, "BoneheadRepo")
        return 0.5