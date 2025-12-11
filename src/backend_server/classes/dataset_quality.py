from __future__ import annotations

import math
from pathlib import Path
from typing import override

from huggingface_hub import HfApi

from src.backend_server.classes.get_exp_coefficient import get_exp_coefficient, score_large_good
from src.backend_server.model.artifact_accessor.name_extraction import extract_name_from_url
from src.backend_server.model.dependencies import DependencyBundle
from src.contracts.artifact_contracts import Artifact, ArtifactType
from src.contracts.metric_std import MetricStd


class DatasetQuality(MetricStd[float]):
    metric_name = "dataset_quality"

    def __init__(self, half_score_point_likes: float, half_score_point_downloads: float,
                 half_score_point_dimensions: float, metric_weight=0.1):
        super().__init__(metric_weight)
        self.api = HfApi()
        self.half_score_point_likes = half_score_point_likes
        self.half_score_point_downloads = half_score_point_downloads
        self.half_score_point_dimensions = half_score_point_dimensions

    def determine_dataset_quality(self, num_likes: int, num_downloads: int, num_dimensions: int) -> float:
        num_likes_score: float = score_large_good(get_exp_coefficient(self.half_score_point_likes), num_likes)
        num_downloads_score: float = score_large_good(get_exp_coefficient(self.half_score_point_downloads),
                                                      num_downloads)
        num_dimensions_score: float = score_large_good(get_exp_coefficient(self.half_score_point_dimensions),
                                                       num_dimensions)
        return (num_likes_score + num_downloads_score + num_dimensions_score) / 3

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle,
                               *args, **kwargs) -> float:
        attached_datasets: list[
                               Artifact] | None = dependency_bundle.db.router_lineage.db_artifact_get_attached_datasets(
            artifact_data.metadata.id)

        if not attached_datasets:
            return 0.0

        quality_scores: list[float] = []
        for dataset in attached_datasets:
            info = self.api.dataset_info(dataset.metadata.name)
            quality_scores.append(self.determine_dataset_quality(info.likes, info.downloads, info.cardData.get("task_categories", [])))

        return sum(quality_scores) / len(quality_scores)
