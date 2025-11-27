from __future__ import annotations

import math
from pathlib import Path
from typing import override

from huggingface_hub import HfApi

from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd


class DBManager:
    pass
class DatasetQuality(MetricStd[float]):
    metric_name = "dataset_quality"

    def __init__(self, half_score_point_likes: float, half_score_point_downloads: float, half_score_point_dimensions: float, metric_weight=0.1):
        super().__init__(metric_weight)
        self.api = HfApi()
        self.half_score_point_likes = half_score_point_likes
        self.half_score_point_downloads = half_score_point_downloads
        self.half_score_point_dimensions = half_score_point_dimensions

    def get_exp_coefficient(self, half_magnitude_point: float):
        return -math.log2(0.5) / half_magnitude_point

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, database_manager: DBManager, *args, **kwargs) -> float:
        repo_id = artifact_data.data.url.rstrip("/").split("datasets/")[-1]

        info = self.api.dataset_info(repo_id, printCLI=False)

        num_likes_score: float = 2 ** (-info.likes * self.get_exp_coefficient(self.half_score_point_likes))
        num_downloads_score: float = 2 ** (-info.downloads * self.get_exp_coefficient(self.half_score_point_downloads))
        num_dimensions_score: float = (
                2 ** (-len(info.cardData.get("task_categories", [])) * self.get_exp_coefficient(self.half_score_point_dimensions)))

        return (num_likes_score + num_downloads_score + num_dimensions_score) / 3

