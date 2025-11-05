from pydantic import validate_call
from src.model.model_rater import ModelRaterEnum
from src.model.external_contracts import ArtifactID, ArtifactType, ArtifactCost


class ArtifactCostAnalyzer:
    @validate_call
    async def get_artifact_cost(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[ModelRaterEnum, ArtifactCost]:
        raise NotImplementedError()
