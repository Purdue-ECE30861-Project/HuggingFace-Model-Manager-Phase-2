from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import override

import requests

from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd
from .get_exp_coefficient import score_large_good, get_exp_coefficient
from ..model.dependencies import DependencyBundle

SHORTLOG_RE = re.compile(r"^\s*(\d+)\s+(.*)$")


class BusFactor(MetricStd[float]):
    metric_name = "bus_factor"

    def __init__(self, contributors_half_score_point: int, metric_weight=0.1) -> None:
        super().__init__(metric_weight)
        self.contributors_half_score_point = contributors_half_score_point

    def parse_shortlog(self, shortlog: str) -> dict[str, int]:
        contribs = {}
        for line in shortlog.splitlines():
            m = SHORTLOG_RE.match(line)
            if not m:
                continue
            count = int(m.group(1))
            name = m.group(2).strip()
            contribs[name] = count
        return contribs

    def hf_contributors(self, url: str, tmpdir: str) -> dict:
        repo_url = url

        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", repo_url, tmpdir],
            check=True,
        )

        result = subprocess.run(
            ["git", "shortlog", "-sn"],
            cwd=tmpdir,
            check=True,
            text=True,
            capture_output=True,
        )

        contributors = self.parse_shortlog(result.stdout)
        return contributors

    def gh_contributors(self, url) -> list:
        headers = {"Accept": "application/vnd.github+json"}

        contributors = []
        page = 1
        per_page = 100

        while True:
            r = requests.get(url, headers=headers,
                             params={"page": page, "per_page": per_page})
            if r.status_code != 200:
                return None

            data = r.json()
            if not data:
                break

            contributors.extend(data)
            page += 1

        return contributors

    def calculate_bus_factor(self, num_contributors_gh: int, num_contributors_hf: int) -> float:
        return score_large_good(get_exp_coefficient(self.contributors_half_score_point),
                                max(num_contributors_gh, num_contributors_hf))

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle,
                               *args, **kwargs) -> float:
        attached_codebase = dependency_bundle.db.router_lineage.db_artifact_get_attached_codebases(
            artifact_data.metadata.id)
        gh_contributors = 0
        if attached_codebase:
            contributors = [len(self.gh_contributors(codebase.data.url)) for codebase in attached_codebase]
            if contributors:
                gh_contributors = sum(contributors) / len(contributors)

        return self.calculate_bus_factor(
            gh_contributors,
            len(self.hf_contributors(artifact_data.data.url, str(ingested_path)))
        )
