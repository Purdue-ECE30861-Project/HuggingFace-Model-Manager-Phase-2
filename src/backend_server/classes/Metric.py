#from __future__ import annotations

from dataclasses import dataclass
from abc import ABC


# =========================
# Metric hierarchy
# =========================

@dataclass
class Metric(ABC):
    def __init__(self, metricName="Metric", metricScore=0, metricWeighting=0.1):
        self.metricName = metricName
        self.metricScore = metricScore         # interpret as 0.0–1.0
        self.metricWeighting = metricWeighting    # 0.0–1.0, contribution to total
        self.metricLatency = 0

    def getMetricName(self) -> str:
        return self.metricName

    def getMetricScore(self) -> float:
        return self.metricScore

    def getWeighting(self) -> float:
        return self.metricWeighting
    
    def getLatency(self) -> int:
        return self.metricLatency