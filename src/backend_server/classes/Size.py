#from __future__ import annotations

from dataclasses import dataclass
from src.classes.Metric import Metric
from src.utils.llm_api import llmAPI
from src.utils.hf_api import hfAPI
import json
import time
import re

@dataclass
class Size(Metric):
    def __init__(self, metricName="Size", metricWeighting=0.1):
        super().__init__(metricName, 0, metricWeighting)
        self.paramCount = 0
        self.device_dict = {}
        self.llm = llmAPI()

    def _score_with_llm(self, url, param_count: int) -> float:
        """Use Purdue’s LLM to contextualize size scoring."""
        prompt = f"""
        You are evaluating the SIZE metric of a machine learning model. This metric needs to assess whether a parameter count is sufficient for a model of a specific use case.

        Information:
        - URL to model: {url}
        - Parameter count: {param_count}

        Rate the model's size on a scale of:
        - 1.0 = Size is appropriate and easy to handle for this type of model
        - 0.5 = Size is large but still manageable or too small and may be too generalizing.
        - 0.0 = Size is unnecessarily large or difficult to use for most purposes or is way too small to be accurate in implementation.

        Answer with only the numeric score (1.0, 0.5, or 0.0).
        """

        try:
            response_text = self.llm.main(prompt)
            PAT = re.compile(r'\b(?:1\.0|0\.5|0\.0)\b')
            match = re.search(PAT, response_text)
            score = float(match.group()) if match else None
            if score:
                return score
            else:
                return 0.0
        except Exception as e:
            print(f"[Size Metric] LLM scoring failed, falling back. Error: {e}")

    def score(self, ratio: float) -> float:
        # ratio = model_size / device_memory
        if ratio <= 0.5:
            return 1.0
        if ratio >= 1.5:
            return 0.0
        return 1.0 - (ratio - 0.5)

    def setSize(self, url):
        """
        Compute size score.
        - If LLM available → ask it to contextualize.
        - Else fallback to rule-based thresholds.
        """
        t0 = time.perf_counter_ns()
        api = hfAPI()
        response = json.loads(api.get_info(url, printCLI=False))

        try:
            parameter_size = response["data"]["safetensors"]["total"]
        except (KeyError, TypeError) as e:
            parameter_size = None

        if parameter_size:
            self.paramCount = parameter_size
        else:
            self.metricScore = 0.0
            dt_ms = (time.perf_counter_ns() - t0) // 1_000_000
            self.metricLatency = dt_ms
            return
        
        GIB = 1024 ** 3
        devices = {
            "raspberry_pi": 1.5 * GIB,
            "jetson_nano": 3.0 * GIB,
            "desktop_pc": 7.0 * GIB,
            "aws_server": 22.0 * GIB,
        }
        model_bytes = self.paramCount * 4
        self.metricLatency = (time.perf_counter_ns() - t0) // 1_000_000
        device_dict = {dev: round(self.score(model_bytes / mem), 3) for dev, mem in devices.items()}
        self.device_dict = device_dict
        self.metricScore = sum(device_dict.values()) / len(device_dict)
        return {dev: round(self.score(model_bytes / mem), 3) for dev, mem in devices.items()}

        # score = self._score_with_llm(url, self.paramCount)
        # if score is not None:
        #     self.metricScore = score
        # else:
        #     self.metricScore = 0.0

        # dt_ms = (time.perf_counter_ns() - t0) // 1_000_000
        # self.metricLatency = dt_ms

    def getSize(self) -> float:
        return self.metricScore

    def getParamCount(self) -> int:
        return self.paramCount