from __future__ import annotations

import pathlib
from pathlib import Path
from typing import override

from pylint.lint import Run
from pylint.reporters import CollectingReporter

from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd
from ..model.dependencies import DependencyBundle


class CodeQuality(MetricStd[float]):
    metric_name = "code_quality"

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle, *args, **kwargs) -> float:
        target = pathlib.Path(ingested_path)
        if not target.exists():
            raise ValueError(f"Path does not exist: {ingested_path}")

        # Use a reporter that captures all messages but does not print anything
        reporter = CollectingReporter()

        # Disable exit on error and disable output
        results = Run([str(ingested_path), "--score=y"], reporter=reporter, exit=False)

        # Extract the global evaluation ("global_note")
        score = results.linter.stats.global_note
        if score is None:
            raise RuntimeError("Pylint did not produce a score.")

        normalized = max(0.0, min(1.0, score / 10.0))
        return normalized