from __future__ import annotations

import math
import re
from pathlib import Path
from typing import override

from src.contracts.artifact_contracts import Artifact
from src.contracts.metric_std import MetricStd
from ..utils.get_metadata import get_collaborators_github, find_github_links
from ..utils.llm_api import llmAPI


class DBManager:
    pass
class BusFactor(MetricStd[float]):
    metric_name = "bus_factor"

    def setNumContributors(self, url, githubURL) -> float:
        if githubURL:
            links = [githubURL]
        else:
            links = find_github_links(url)
        if links:
            avg, std, authors = get_collaborators_github(links[0], n=200)
            if avg == 0:
                evenness = 0
                groupsize = 0
            else:
                evenness = 1.0 / (1.0 + (std / avg) **2) # rewards balanced contribution, penalizes concentration
                saturation_coeff = 5
                groupsize = 1 - math.exp((-1.0 / avg) / saturation_coeff)
            self.NumContributors = len(authors)
            return round(evenness * groupsize, 3)
        else:
            api = llmAPI()
            prompt = "Given this link to a HuggingFace model repository, can you assess the Bus Factor of the model based on size of the organization/members \
                and likelihood that the work for developing this model was evenly split but all contributors. \
                I would like you to return a single value from 0-1 with 1 being perfect bus factor and no risk involved, and 0 being one singular contributor doing all the work. \
                This response should just be the 0-1 value with no other text given."
            response = api.main(f"URL: {url}, instructions: {prompt}")
            PAT = re.compile(r'\b(?:1\.0|0\.5|0\.0)\b')
            match = re.search(PAT, response)
            bus_factor = float(match.group()) if match else None
            if bus_factor:
                return round(bus_factor, 3)
        return 0.0

    @override
    def calculate_metric_score(self, ingested_path: Path, artifact_data: Artifact, database_manager: DBManager, *args, **kwargs) -> float:
        #return self.setNumContributors(artifact_data.url, "BoneheadRepo")
        return 0.5
