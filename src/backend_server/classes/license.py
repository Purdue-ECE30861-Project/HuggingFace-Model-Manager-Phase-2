#from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Union, override

from src.backend_server.model.dependencies import DependencyBundle
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd


class DBManager:
    pass
HIGH_PERMISSIVE = {
    "mit", "bsd-2-clause", "bsd-3-clause",
    "apache-2.0", "lgpl-2.1", "lgpl-3.0",
    "mpl-2.0", "cc-by-4.0",
    "openrail-m", "bigscience-openrail-m",
}

RESTRICTIVE = {
    # non-commercial / research-only families
    "cc-by-nc", "cc-by-nc-4.0", "rail-nc", "openrail-nc",
    "creativeml-openrail-non-commercial",
    # your policy choice: AGPL often treated as problematic for redistribution
    "agpl-3.0", "agpl-3.0-only", "agpl-3.0-or-later",
}

ALIASES = {
    "bsd-2": "bsd-2-clause",
    "bsd-3": "bsd-3-clause",
    "bsl-1.0": "bsl-1.0",  # example if you later score Boost
    "gpl-3.0": "gpl-3.0",  # keep around if you classify GPL differently
    "openrail-m-v1": "openrail-m",
}

NC_PATTERNS = re.compile(r"(non[\s-]*commercial|research[\s-]*only|no[\s-]*derivatives|noai|no-ai)", re.I)

def _norm(s: str) -> str:
    # strip parentheses notes, lowercase, normalize separators
    s = re.sub(r"\(.*?\)", "", s).strip().lower()
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "-", s)
    return ALIASES.get(s, s)

def _as_list(lic: Union[str, Iterable[str], None]):
    if lic is None:
        return []
    if isinstance(lic, (list, tuple, set)):
        return list(lic)
    return [lic]

class License(MetricStd[float]):
    metric_name = "license"

    def __init__(self, metric_weight=0.1) -> None:
        super().__init__(metric_weight)

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle, *args, **kwargs) -> float:
        #return self.evaluate(artifact_data.data.url)
        return 0.5
