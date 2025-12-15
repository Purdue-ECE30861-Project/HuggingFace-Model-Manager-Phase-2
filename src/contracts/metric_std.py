import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar, Generic

from .artifact_contracts import Artifact
from ..backend_server.model.dependencies import DependencyBundle

#from ..backend_server.model.data_store.database_connectors.mother_db_connector import DBManager


logger = logging.getLogger(__name__)
T = TypeVar("T")


class MetricStd(ABC, Generic[T]):
    metric_name: str = "NoName"
    def __init__(self, metric_weight=0.1):
        self.metric_weight = metric_weight
        self.ingested_path: Path|None = None
        self.artifact_data: Artifact|None = None

    def set_params(self, ingested_path: Path, artifact_data: Artifact) -> "MetricStd":
        self.ingested_path = ingested_path
        self.artifact_data = artifact_data

        return self

    def get_metric_name(self) -> str:
        return self.metric_name

    def get_weight(self) -> float:
        return self.metric_weight

    def run_score_calculation(self, dependency_bundle: DependencyBundle, *args, **kwargs) -> tuple[str, float, T, T]:
        start_time = time.time()

        metric_score = 0
        try:
            metric_score = self.calculate_metric_score(self.ingested_path, self.artifact_data, dependency_bundle, *args, **kwargs)
            if metric_score > 1.0 or metric_score < 0.0:
                raise ValueError(f"The raw metric score for {self.metric_name} must be normalized between 0 and 1")
        except Exception as e:
            logger.error(f"{self.metric_name} FAILED DUE TO {e}")

        metric_score_weighted = self.metric_weight * metric_score
        end_time = time.time()

        print(f"METRIC: {self.metric_name} FINISHED")
        return self.metric_name, end_time - start_time, metric_score, metric_score_weighted

    @abstractmethod
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependencies: DependencyBundle, *args, **kwargs) -> T:
        raise NotImplementedError()