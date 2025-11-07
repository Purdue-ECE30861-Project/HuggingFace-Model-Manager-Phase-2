#from __future__ import annotations

import json
import logging
import time
from typing import Dict, Optional, Tuple, Any

from Metric import Metric
from ..utils.llm_api import llmAPI
from ..utils.hf_api import hfAPI
import re
from typing import Iterable, Union

HIGH_PERMISSIVE = {
    "mit", "bsd-2-clause", "bsd-3-clause",
    "apache-2.0", "lgpl-2.1", "lgpl-3.0",
    "mpl-2.0", "cc-by-4.0",
    "openrail-m", "bigscience-openrail-m",
}

RESTRICTIVE = {
    # non-commercial / research-only families
    "cc-by-nc", "cc-by-nc-4.0", "rail-nc", "openrail-nc",
    "creativeml-openrail-non-commercial",
    # your policy choice: AGPL often treated as problematic for redistribution
    "agpl-3.0", "agpl-3.0-only", "agpl-3.0-or-later",
}

ALIASES = {
    "bsd-2": "bsd-2-clause",
    "bsd-3": "bsd-3-clause",
    "bsl-1.0": "bsl-1.0",  # example if you later score Boost
    "gpl-3.0": "gpl-3.0",  # keep around if you classify GPL differently
    "openrail-m-v1": "openrail-m",
}

NC_PATTERNS = re.compile(r"(non[\s-]*commercial|research[\s-]*only|no[\s-]*derivatives|noai|no-ai)", re.I)

def _norm(s: str) -> str:
    # strip parentheses notes, lowercase, normalize separators
    s = re.sub(r"\(.*?\)", "", s).strip().lower()
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "-", s)
    return ALIASES.get(s, s)

def _as_list(lic: Union[str, Iterable[str], None]):
    if lic is None:
        return []
    if isinstance(lic, (list, tuple, set)):
        return list(lic)
    return [lic]

class License(Metric):
    def __init__(self, metricName: str = "License", metricWeighting: float = 0.1) -> None:
        super().__init__(metricName, 0.0, metricWeighting)
        self.license: float = 0.0     
        self.llm = llmAPI()   

    def score_license(self, license_value: Union[str, Iterable[str], None]) -> float:
        items = [_norm(x) for x in _as_list(license_value)]
        if not items:
            return 0.3

        # If any explicit restrictive match or NC-style phrase -> 0.0
        if any(x in RESTRICTIVE or NC_PATTERNS.search(x) for x in items):
            return 0.0

        # If any permissive and none restrictive -> 1.0
        if any(x in HIGH_PERMISSIVE for x in items):
            return 1.0

        # Default grey area
        return 0.3

    def evaluate(self, url) -> float:
        t0 = time.perf_counter_ns()
        api = hfAPI()
        response = api.get_info(url, printCLI=False)
        try:
            tag_license = response["data"]["tags"]["license"]
        except (KeyError, TypeError):
            tag_license = None
        try:
            cardData_license = response["data"]["cardData"]["license"]
        except (KeyError, TypeError):
            cardData_license = None

        if tag_license:
            return (self.score_license(tag_license), time.perf_counter_ns() - t0)
        elif cardData_license:
            return (self.score_license(cardData_license), time.perf_counter_ns() - t0)
        else:
            #GenAI prompt
            prompt = (
                f"You are a licensing analyst. A url to a huggingface model is provided: {url} Score license compatibility relative to LGPL-2.1.\n"
                "Respond with ONLY a single JSON object:\n"
                '  { "license_score": number in [0,1],'
                '    "license_normalized": string,'
                '    "reason": string }\n'
                "Scoring:\n"
                "  1.0: MIT, BSD-2/3, Apache-2.0, LGPL-2.1/3.0, MPL-2.0, CC-BY-4.0 (weights), OpenRAIL-M (commercial OK)\n"
                "  0.0: Non-commercial (e.g., CC-BY-NC, RAIL-NC), AGPL-3.0, custom terms restricting commercial redistribution\n"
                "  0.3: Unclear/unknown\n"
                "Prefer explicit SPDX IDs or LICENSE links."
            )

            #GenAI call
            score = 0.3        #default for unclear
            try:
                resp = self.llm.main(prompt)
                if isinstance(resp, str):
                    resp = json.loads(resp)
                if isinstance(resp, dict):
                    score = float(resp.get("license_score", score))
            except Exception as e:
                logging.exception("License.evaluate GenAI error: %s", e)

            #clamp + store on the metric object
            score = max(0.0, min(1.0, score))
            self.license = score
            self.metricScore = score

        dt_ms = (time.perf_counter_ns() - t0) // 1_000_000
        return score, dt_ms
