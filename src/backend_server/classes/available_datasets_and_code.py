from __future__ import annotations

from pathlib import Path

from typing_extensions import override

from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd


class DBManager:
    pass
class AvailableDatasetAndCode(MetricStd[float]):
    metric_name = "dataset_and_code_score"

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, database_manager: DBManager, *args, **kwargs) -> float:
        attached_datasets = database_manager.router_lineage.db_artifact_get_attached_datasets(artifact_data.metadata.id)
        attached_codebases = database_manager.router_lineage.db_artifact_get_attached_codebases(artifact_data.metadata.id)

        score: float = 0.0
        if attached_datasets:
            score += 0.5
        if attached_codebases:
            score += 0.5

        return score