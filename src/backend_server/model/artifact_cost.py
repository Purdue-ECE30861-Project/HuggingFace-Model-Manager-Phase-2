from pydantic import validate_call
from ..model.model_rater import ModelRaterEnum
from src.contracts.artifact_contracts import ArtifactID, ArtifactType, ArtifactCost


class ArtifactCostAnalyzer:
    @validate_call
    async def get_artifact_cost(self, artifact_type: ArtifactType, id: ArtifactID, dependency: bool) -> tuple[ModelRaterEnum, ArtifactCost]:
        raise NotImplementedError()
