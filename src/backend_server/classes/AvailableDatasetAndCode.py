#from __future__ import annotations
from dataclasses import dataclass
from src.classes.Metric import Metric
from src.utils.get_metadata import find_dataset_links, find_github_links
import time

@dataclass
class AvailableDatasetAndCode(Metric):
    def __init__(self, metricName="Available Dataset and Code", metricWeighting=0.2, datasetAvailable=False, codeAvailable=False):
        super().__init__(metricName, 0, metricWeighting)
        
    
    def score_dataset_availability(self, url: str, datasetURL) -> float:
        """
        Returns a score between 0 and 1 for dataset availability in a Hugging Face model.
        0 = no datasets mentioned
        0.5 = at least one dataset mentioned, but unclear (non-HF or weak link)
        1.0 = at least one Hugging Face dataset explicitly linked
        """
        if datasetURL:
            dataset_links = [datasetURL]
        else:
            dataset_links = find_dataset_links(url)

        if not dataset_links:
            return 0.0

        # Score higher if HF dataset links are explicitly present
        hf_links = [ds for ds in dataset_links if "huggingface.co/datasets" in ds]
        if hf_links:
            return 1.0

        # If datasets mentioned but not on HF, partial score
        return 0.5
    
    def score_code_availability(self, url: str, githubURL) -> float:
        """
        Returns a score between 0 and 1 for code availability in a Hugging Face model.
        0   = no GitHub (or external code) links
        0.5 = some GitHub links present, but repo might be unrelated / unclear
        1.0 = at least one clear GitHub repo link (likely the model's codebase)
        """
        if githubURL:
            github_links = [githubURL]
        else:
            github_links = find_github_links(url)

        if not github_links:
            return 0.0

        # Heuristic: If there's a GitHub link, assume at least partial code availability
        # We could strengthen this by checking for keywords in the repo name like "model",
        # "training", "code", etc.
        for link in github_links:
            repo_name = link.split("/")[-1].lower()
            if any(keyword in repo_name for keyword in ["model", "train", "code", "repo"]):
                return 1.0

        # Otherwise just give partial credit for mentioning GitHub
        return 0.5


    def score_dataset_and_code_availability(self, url: str, datasetURL, githubURL) -> float:
        """
        Combine dataset and code availability scores into a single score (0–1).
        
        Strategy:
        - Equal weighting of dataset availability (50%) and code availability (50%)
        - If both are fully available, score = 1.0
        - If neither available, score = 0.0
        - Otherwise returns a value in between
        """
        t0 = time.perf_counter_ns()
        dataset_score = self.score_dataset_availability(url, datasetURL)
        code_score = self.score_code_availability(url, githubURL)

        total_score = 0.5 * dataset_score + 0.5 * code_score
        dt_ms = (time.perf_counter_ns() - t0) // 1_000_000
        return round(total_score, 3), dt_ms