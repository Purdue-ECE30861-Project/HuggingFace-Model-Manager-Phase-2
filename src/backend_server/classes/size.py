#from __future__ import annotations
import logging
from dataclasses import dataclass

from typing_extensions import override

from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
from src.backend_server.utils.llm_api import llmAPI
from src.backend_server.utils.hf_api import hfAPI
from pathlib import Path
from src.contracts.artifact_contracts import Artifact, SizeScore, ArtifactCost
from src.contracts.metric_std import MetricStd
import json
import time
import re


logger = logging.getLogger(__name__)


class Size(MetricStd[SizeScore]):
    metric_name = "size_score"

    def __init__(self, rpi_max_size_mb: float, jsn_max_size_mb: float, dpc_max_size_mb: float, aws_max_size_mb: float, metric_weight=0.1):
        super().__init__(metric_weight)
        self.rpi_max_size_mb = rpi_max_size_mb
        self.jsn_max_size_mb = jsn_max_size_mb
        self.dpc_max_size_mb = dpc_max_size_mb
        self.aws_max_size_mb = aws_max_size_mb

    def calculate_size_score_with_max_size(self, max_size: float, size: float) -> float:
        adjusted_score = max_size - size
        if adjusted_score < 0.0:
            return 0.0
        return adjusted_score / max_size

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, database_manager: DBManager, *args, **kwargs) -> SizeScore:
        return_value: SizeScore = SizeScore(
            raspberry_pi=0.0,
            jetson_nano=0.0,
            desktop_pc=0.0,
            aws_server=0.0
        )
        artifact_size: ArtifactCost|None = database_manager.router_cost.db_artifact_cost(artifact_data.metadata.id, artifact_data.metadata.type, False)
        if not artifact_size:
            logger.error(f"Artifact '{artifact_data.metadata.id}' has no size")
            return return_value

        return_value.raspberry_pi = self.calculate_size_score_with_max_size(self.rpi_max_size_mb, artifact_size.standalone_cost)
        return_value.jetson_nano = self.calculate_size_score_with_max_size(self.jsn_max_size_mb, artifact_size.standalone_cost)
        return_value.desktop_pc = self.calculate_size_score_with_max_size(self.dpc_max_size_mb, artifact_size.standalone_cost)
        return_value.aws_server = self.calculate_size_score_with_max_size(self.aws_max_size_mb, artifact_size.standalone_cost)

        return return_value