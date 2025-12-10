from __future__ import annotations

import os
import re
from pathlib import Path
from typing import override

from huggingface_hub import HfApi

from src.backend_server.classes.get_exp_coefficient import get_exp_coefficient, score_large_bad, score_large_good
from src.backend_server.model.dependencies import DependencyBundle
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd

ARXIV_RE = re.compile(
    r"(https?://arxiv\.org/(abs|pdf)/\d{4}\.\d{4,5}(?:\.pdf)?)|"
    r"(arXiv:\d{4}\.\d{4,5})",
    re.IGNORECASE
)

def has_any(root, names):
    return any(os.path.isdir(os.path.join(root, n)) for n in names)


class RampUpTime(MetricStd[float]):
    metric_name = "ramp_up_time"

    def __init__(self, directory_breadth_half_score_point: int, directory_depth_half_score_point: int,
                 arxiv_link_half_score_point: int, num_spaces_half_score_point: int, metric_weight=0.1):
        super().__init__(metric_weight)
        self.directory_breadth_half_score_point = directory_breadth_half_score_point
        self.directory_depth_half_score_point = directory_depth_half_score_point
        self.arxiv_link_half_score_point = arxiv_link_half_score_point
        self.num_spaces_half_score_point = num_spaces_half_score_point

    def num_spaces_calculator(self, model_name: str) -> int:
        api = HfApi()
        
        try:
            model_info = api.model_info(model_name)
            return len(model_info.spaces)
        except:
            return 0

    def num_spaces_score(self, num_spaces: int) -> float:
        return score_large_good(get_exp_coefficient(self.num_spaces_half_score_point), num_spaces)

    def directory_depth_calculation(self, path: Path, depth: int) -> float:
        children = [child for child in path.iterdir() if child.is_dir()]
        if not children:
            return depth

        max_depth = 0
        for child in children:
            child_path = path / child
            child_depth = self.directory_depth_calculation(child_path, depth + 1)
            if child_depth > max_depth:
                max_depth = child_depth
        return max_depth

    def directory_size_calculation(self, root_path: Path):
        dir_count = 0
        file_count = 0

        for _, dirs, files in os.walk(root_path):
            dir_count += len(dirs)
            file_count += len(files)

        files_per_dir = file_count / dir_count
        breadth_score = score_large_bad(get_exp_coefficient(self.directory_breadth_half_score_point), files_per_dir)
        root_path_depth = self.directory_depth_calculation(root_path, 0)
        depth_score = score_large_bad(get_exp_coefficient(self.directory_depth_half_score_point), root_path_depth)

        return (breadth_score + depth_score) / 2

    def directory_check_arxiv_links(self, root: Path) -> float:
        matches = {}  # file -> list of matches

        for dirpath, _, files in os.walk(root):
            for f in files:
                path = os.path.join(dirpath, f)
                try:
                    with open(path, "r", errors="ignore") as fh:
                        text = fh.read()
                except Exception:
                    continue

                found = ARXIV_RE.findall(text)
                if found:
                    # flatten regex groups
                    cleaned = {m[0] or m[2] for m in found}
                    matches[path] = list(cleaned)

        arxiv_score = score_large_good(get_exp_coefficient(self.arxiv_link_half_score_point), len(matches))
        return arxiv_score

    def directory_check_structure(self, root: Path) -> float:
        values = {
            "has_src": int(has_any(root, ["src"])),
            "has_scripts": int(has_any(root, ["scripts"])),
            "has_configs": int(has_any(root, ["configs", "config"])),
            "has_tests": int(has_any(root, ["tests", "test"])),
            "has_docs": int(has_any(root, ["docs", "documentation"])),
            "has_examples": int(has_any(root, ["examples", "example"])),
            "has_demo": int(has_any(root, ["demo", "demos"])),
            "has_notebooks": int(has_any(root, ["notebooks", "notebook"])),
        }

        return sum(values.values()) / len(values)

    import os

    def detect_install_instructions(self, root):
        specific = ("pip install", "apt install", "conda install")
        install_any = "install"

        has_generic = False

        for dirpath, _, files in os.walk(root):
            for f in files:
                path = os.path.join(dirpath, f)

                if not f.lower().endswith((
                        ".md", ".txt", ".rst", ".cfg", ".ini", ".yaml", ".yml"
                )):
                    continue

                try:
                    text = open(path, "r", errors="ignore").read().lower()
                except Exception:
                    continue

                if any(s in text for s in specific):
                    return 1.0

                if install_any in text:
                    has_generic = True

        if has_generic:
            return 0.5
        return 0.0

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle,
                               *args, **kwargs) -> float:
        score_calculations = [
            self.directory_size_calculation(ingested_path),
            self.directory_check_arxiv_links(ingested_path),
            self.directory_check_structure(ingested_path),
            self.detect_install_instructions(ingested_path),
            self.num_spaces_score(self.num_spaces_calculator(artifact_data.metadata.name))
        ]

        score_weighted = sum([score / len(score_calculations) for score in score_calculations])

        return score_weighted
