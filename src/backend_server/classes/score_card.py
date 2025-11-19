#from __future__ import annotations
from dataclasses import dataclass
from src.classes.AvailableDatasetAndCode import AvailableDatasetAndCode
from src.classes.BusFactor import BusFactor
from src.classes.CodeQuality import CodeQuality
from src.classes.DatasetQuality import DatasetQuality
from license import License
from Metric import Metric
from performance_claims import PerformanceClaims
from ramp_up_time import RampUpTime
from size import Size
from threading import MetricRunner
from src.utils.get_metadata import get_github_readme
import json
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

@dataclass
class ScoreCard:
    def __init__(self, url: str):
        logger.info(f"Initializing ScoreCard for {url}")
        self.url = url
        self.datasetURL = None
        self.githubURL = None
        self.totalScore = 0.0
        
        # Initialize all metrics
        logger.debug("Initializing metrics...")
        self.busFactor = BusFactor()
        self.datasetQuality = DatasetQuality()
        self.size = Size()
        self.license = License()
        self.rampUpTime = RampUpTime()
        self.performanceClaims = PerformanceClaims()
        self.codeQuality = CodeQuality()
        self.availableDatasetAndCode = AvailableDatasetAndCode()
        
        logger.debug("Fetching README...")
        try:
            self.readme_text = get_github_readme(url)
            logger.debug(f"README fetched")
        except Exception as e:
            logger.warning(f"Failed to fetch README: {e}")
            self.readme_text = ""
        
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
    
    def setTotalScore(self):
        """
        Compute all metric scores.
        
        Args:
            use_multiprocessing: If True, run tasks in parallel using multiprocessing.
                               If False, run tasks sequentially (useful for testing).
        """
        
        try:
            runner = MetricRunner(num_processes=4)
            
            # Add all metric computation tasks
            logger.debug("Adding metric tasks...")
            runner.add_task(self.busFactor, 'setNumContributors', self.url, self.githubURL)
            runner.add_task(self.datasetQuality, 'computeDatasetQuality', self.url, self.datasetURL)
            runner.add_task(self.size, 'setSize', self.url)
            runner.add_task(self.license, 'evaluate', self.url)
            runner.add_task(self.rampUpTime, 'setRampUpTime', self.readme_text)
            runner.add_task(self.performanceClaims, 'evaluate', self.url)
            runner.add_task(self.codeQuality, 'evaluate', self.url, self.githubURL)
            runner.add_task(self.availableDatasetAndCode, 'score_dataset_and_code_availability', self.url, self.datasetURL, self.githubURL)
            
            # Execute all tasks in parallel
            logger.debug("Running metric tasks in parallel...")
            results = runner.run()
            
            # Process results and handle errors
            logger.debug("Processing metric results...")
            for metric, result, error in results:
                metric_name = metric.getMetricName()
                
                if error:
                    # Log error but continue with other metrics
                    logger.debug(f"Error details for {metric_name}: {error}")
                    # Find the actual metric object in self and set to 0
                    actual_metric = self.find_metric_by_name(metric_name)
                    if actual_metric:
                        actual_metric.metricScore = 0.0
                        actual_metric.metricLatency = 0
                else:
                    # Find the actual metric object in self
                    actual_metric = self.find_metric_by_name(metric_name)
                    if not actual_metric:
                        logger.warning(f"Could not find metric object for {metric_name}")
                        continue
                    
                    # Update metric with result
                    if isinstance(result, tuple) and len(result) == 2:
                        score, latency = result
                        actual_metric.metricScore = score
                        actual_metric.metricLatency = latency
                        logger.debug(f"{metric_name}: score={score}, latency={latency}ms")
                    elif result is None:
                        # Method didn't return anything, but modified the metric in child process
                        score = metric.getMetricScore()
                        latency = metric.getLatency()
                        actual_metric.metricScore = score
                        actual_metric.metricLatency = latency
                        logger.debug(f"{metric_name}: score={score}, latency={latency}ms (from returned metric)")
                    elif isinstance(result, dict):
                        # Special case for Size metric which returns device_dict
                        actual_metric.device_dict = result
                        score = metric.getMetricScore()
                        latency = metric.getLatency()
                        actual_metric.metricScore = score
                        actual_metric.metricLatency = latency
                        logger.debug(f"{metric_name}: score={score}, latency={latency}ms (dict result)")
                    else:
                        logger.warning(f"{metric_name} returned unexpected result type: {type(result)}")
                        actual_metric.metricScore = 0.0
                        actual_metric.metricLatency = 0
            
            # Calculate total weighted score
            logger.debug("Calculating total weighted score...")
            total_weight = 0.0
            weighted_sum = 0.0
            
            for metric in self.get_all_metrics():
                weight = metric.getWeighting()
                score = metric.getMetricScore()
                metric_name = metric.getMetricName()
                
                logger.debug(f"{metric_name}: weight={weight}, score={score}")
                
                weighted_sum += score * weight
                total_weight += weight
            
            if total_weight > 0:
                self.totalScore = round(weighted_sum / total_weight, 3)
            else:
                logger.warning("Total weight is 0, setting total score to 0")
                self.totalScore = 0.0
            
            logger.info(f"Total score for {self.modelName}: {self.totalScore}")
            
        except Exception as e:
            logger.warning(f"Failed to compute total score: {e}")
            
    def find_metric_by_name(self, name: str):
        """
        Find a metric object by its name.
        """
        for metric in self.get_all_metrics():
            if metric.getMetricName() == name:
                return metric
        return None
    
    def get_all_metrics(self):
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
    
    def printScores(self):
        output = {
            "name": self.modelName,
            "category": "MODEL",
            "net_score": round(self.totalScore, 3),
            "net_score_latency": sum(m.getLatency() for m in self.get_all_metrics()),
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