#from __future__ import annotations

from dataclasses import dataclass
from src.classes.AvailableDatasetAndCode import AvailableDatasetAndCode
from src.classes.BusFactor import BusFactor
from src.classes.CodeQuality import CodeQuality
from src.classes.DatasetQuality import DatasetQuality
from src.classes.License import License
from src.classes.Metric import Metric
from src.classes.PerformanceClaims import PerformanceClaims
from src.classes.RampUpTime import RampUpTime
from src.classes.Size import Size
from src.classes.Threading import MetricRunner
from src.utils.get_metadata import get_github_readme
#from src.utils.get_metadata import get_model_metadata
#import time
import json
from urllib.parse import urlparse

@dataclass
class ScoreCard:
    def __init__(self, url: str):
        #t0 = time.perf_counter_ns()
        self.url = url
        self.datasetURL = None
        self.githubURL = None
        self.totalScore = 0.0

        # Initialize all metrics
        self.busFactor = BusFactor()
        self.datasetQuality = DatasetQuality()
        self.size = Size()
        self.license = License()
        self.rampUpTime = RampUpTime()
        self.performanceClaims = PerformanceClaims()
        self.codeQuality = CodeQuality()
        self.availableDatasetAndCode = AvailableDatasetAndCode()
        
        self.readme_text = get_github_readme(url)
        self.modelName = self.getName(url)
        

    def setGithubURL(self, url: str):
        self.githubURL = url
    
    def setDatasetURL(self, url: str):
        self.datasetURL = url
    
    def getName(self, url: str) -> str:
        p = urlparse(url)
        parts = [seg for seg in p.path.split("/") if seg]
        if len(parts) < 2:
            raise ValueError("Invalid HF URL; expected https://huggingface.co/<owner>/<repo>")
        return parts[1]

    def setTotalScore(self, use_multiprocessing=True):
        """
        Compute all metric scores.
        
        Args:
            use_multiprocessing: If True, run tasks in parallel using multiprocessing.
                               If False, run tasks sequentially (useful for testing).
        """
        tasks = [
            (self.busFactor, 'setNumContributors', (self.url, self.githubURL), {}),
            (self.datasetQuality, 'computeDatasetQuality', (self.url, self.datasetURL), {}),
            (self.size, 'setSize', (self.url,), {}),
            (self.license, 'evaluate', (self.url,), {}),
            (self.rampUpTime, 'setRampUpTime', (self.readme_text,), {}),
            (self.performanceClaims, 'evaluate', (self.url,), {}),
            (self.codeQuality, 'evaluate', (self.url, self.githubURL), {}),
            (self.availableDatasetAndCode, 'score_dataset_and_code_availability', (self.url, self.datasetURL, self.githubURL), {})
        ]

        if use_multiprocessing:
            runner = MetricRunner(num_processes=4)
            for metric, method_name, args, kwargs in tasks:
                runner.add_task(metric, method_name, *args, **kwargs)
            results = runner.run()
        else:
            # Run tasks sequentially for testing
            results = []
            for metric, method_name, args, kwargs in tasks:
                try:
                    method = getattr(metric, method_name)
                    result = method(*args, **kwargs)
                    results.append((metric, result, None))
                except Exception as e:
                    error_info = {
                        "message": str(e),
                        "metric": metric.getMetricName() if hasattr(metric, 'getMetricName') else str(metric),
                    }
                    results.append((metric, None, error_info))
        
        # Process results and handle errors
        for metric, result, error in results:
            if error:
                # Log error but continue with other metrics
                print(f"Error computing {metric.getMetricName()}: {error['message']}", flush=True)
                metric.metricScore = 0.0
                metric.metricLatency = 0
            else:
                # Update metric with result
                if isinstance(result, tuple) and len(result) == 2:
                    score, latency = result
                    metric.metricScore = score
                    metric.metricLatency = latency
        
        # Calculate total weighted score
        total_weight = 0.0
        weighted_sum = 0.0
        total_latency = 0
        for metric in self._get_all_metrics():
            total_latency += metric.getLatency()
            weight = metric.getWeighting()
            score = metric.getMetricScore()
            weighted_sum += score * weight
            total_weight += weight
        self.total_latency = total_latency
        if total_weight > 0:
            self.totalScore = round(weighted_sum / total_weight, 3)
        else:
            self.totalScore = 0.0
            
    def _get_all_metrics(self) -> list[Metric]:
        return [
            self.availableDatasetAndCode,
            self.busFactor,
            self.codeQuality,
            self.datasetQuality,
            self.license,
            self.performanceClaims,
            self.rampUpTime,
            self.size
        ]

    def getTotalScore(self) -> float:
        return self.totalScore
    
    def getLatency(self) -> int:
        return self.total_latency

    def printScores(self):
        output = {
            "name": self.modelName,
            "category": "MODEL",
            "net_score": round(self.totalScore, 3),
            "net_score_latency": sum(m.getLatency() for m in self._get_all_metrics()),
            "ramp_up_time": round(self.rampUpTime.getMetricScore(), 3),
            "ramp_up_time_latency": self.rampUpTime.getLatency(),
            "bus_factor": round(self.busFactor.getMetricScore(), 3),
            "bus_factor_latency": self.busFactor.getLatency(),
            "performance_claims": round(self.performanceClaims.getMetricScore(), 3),
            "performance_claims_latency": self.performanceClaims.getLatency(),
            "license": round(self.license.getMetricScore(), 3),
            "license_latency": self.license.getLatency(),
            "size_score": self.size.device_dict,  # Dictionary of device -> score
            "size_score_latency": self.size.getLatency(),
            "dataset_and_code_score": round(self.availableDatasetAndCode.getMetricScore(), 3),
            "dataset_and_code_score_latency": self.availableDatasetAndCode.getLatency(),
            "dataset_quality": round(self.datasetQuality.getMetricScore(), 3),
            "dataset_quality_latency": self.datasetQuality.getLatency(),
            "code_quality": round(self.codeQuality.getMetricScore(), 3),
            "code_quality_latency": self.codeQuality.getLatency()
        }

        print(json.dumps(output))