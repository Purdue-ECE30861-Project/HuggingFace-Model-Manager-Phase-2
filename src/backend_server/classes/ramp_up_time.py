from __future__ import annotations

from pathlib import Path
from typing import override

from src.backend_server.model.dependencies import DependencyBundle
from src.backend_server.utils.llm_api import LLMAccessor
from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd


class RampUpTime(MetricStd[float]):
    metric_name = "ramp_up_time"

    def _score_readme_with_llm(self, readme_text: str) -> float:
        """Send README text to Purdue’s LLM and return 0.0, 0.5, or 1.0."""
        # PLEASE NO MORE STUPID FUCKING AI PLEASE
        prompt = f"""
        Evaluate the documentation quality of an open-source machine learning project.
        The goal is to rate how quickly a new engineer could understand and use the project based on its README.

        Read the README text below and assign one of the following scores:
        - 1.0 = Excellent documentation (clear setup instructions, examples, usage details, dependencies, etc.)
        - 0.5 = Moderate documentation (some instructions exist, but incomplete or unclear)
        - 0.0 = Poor documentation (very little or no usable information)

        README text:
        ---
        {readme_text[:8000]}
        ---

        Answer with only the numeric score (1.0, 0.5, or 0.0).
        """

        response_text = self.llm.main(prompt)

        if "1.0" in response_text:
            return 1.0
        elif "0.5" in response_text:
            return 0.5
        else:
            return 0.0

    def setRampUpTime(self, readme_text: str):
        """
        Set ramp-up time score either from:
        - precomputed_score (manual value for testing), or
        - raw readme_text (evaluated by LLM).
        """
        if readme_text:
            return self._score_readme_with_llm(readme_text)
        else:
            return 0.0

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, dependency_bundle: DependencyBundle, *args, **kwargs) -> float:
        # readme_files = [p for p in Path.rglob('*') if p.is_file() and p.name.lower().startswith("readme")]
        # contents = []
        # for f in readme_files:
        #     try:
        #         contents.append(f.read_text(encoding="utf-8"))
        #     except Exception:
        #         continue
        # readme = "\n\n".join(contents)
        #
        # return self.setRampUpTime(readme)
        return 0.5
