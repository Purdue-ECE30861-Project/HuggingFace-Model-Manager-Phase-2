#from __future__ import annotations
from dataclasses import dataclass
from src.classes.Metric import Metric
from src.utils.hf_api import hfAPI
from src.utils.get_metadata import find_dataset_links
import re
import math
import json
import time
from typing import Tuple

@dataclass
class DatasetQuality(Metric):
    def __init__(self, metricName="Dataset Quality", metricWeighting = 0.1, datasetShape=(0), datasetEntries=0):
        super().__init__(metricName, 0, metricWeighting)
    
    
    def _score_single_dataset(self, dataset_info: dict) -> float:
        """
        Compute a dataset quality score for one dataset.
        Uses likes, downloads, license, and optional test/dimension metadata.
        """
        likes = dataset_info.get("likes", 0)
        downloads = dataset_info.get("downloads", 0)
        license_str = dataset_info.get("license", None)
        dimensions = dataset_info.get("cardData", {}).get("task_categories", [])  # heuristic
        num_dimensions = len(dimensions)

        # Popularity proxy
        likes_score = math.log(likes + 1) / math.log(5000 + 1)

        # Adoption proxy
        downloads_score = math.log(downloads + 1) / math.log(1_000_000 + 1)

        # License quality
        if license_str is None:
            license_score = 0.2
        elif any(x in license_str.lower() for x in ["mit", "apache", "cc0", "cc-by"]):
            license_score = 1.0
        elif "research" in license_str.lower():
            license_score = 0.8
        else:
            license_score = 0.5

        # Extra signal: more dimensions/tests = more robust dataset
        dimension_score = min(num_dimensions / 10.0, 1.0)  # cap at 1

        # Weighted combination
        total_score = (
            0.3 * likes_score
            + 0.3 * downloads_score
            + 0.3 * license_score
            + 0.1 * dimension_score
        )

        return round(min(total_score, 1.0), 3)

    def computeDatasetQuality(self, url: str, datasetURL: str) -> Tuple[float, int]:
        """
        For a Hugging Face model URL:
        - Find dataset links mentioned in the model card
        - Compute quality scores for each dataset
        - Return an aggregated score (average across datasets)
        """
        t0 = time.perf_counter_ns()
        if datasetURL:
            dataset_links = [datasetURL]
        else:
            dataset_links = find_dataset_links(url)
        if not dataset_links:
            return 0.0, 0

        scores = []
        api = hfAPI()
        for link in dataset_links:
            dataset_info_str = api.get_info(link, printCLI=False)
            dataset_info = json.loads(dataset_info_str).get("data", {})
            score = self._score_single_dataset(dataset_info)
            scores.append(score)

        if not scores:
            dt_ms = (time.perf_counter_ns() - t0) / 1_000_000
            return 0.0, dt_ms

        # Aggregate: average across datasets
        dt_ms = (time.perf_counter_ns() - t0) // 1_000_000
        return round(sum(scores) / len(scores), 3), dt_ms

        