from fastapi import Depends, APIRouter, HTTPException, status, Response
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError

from src.model.external_contracts import ArtifactID, ArtifactType, ArtifactCost
from src.model.artifact_cost import ArtifactCostAnalyzer
from src.model.model_rater import ModelRaterEnum
from src.frontend_controller.authentication.auth_object import AccessLevel, access_level, VerifyAuth
from src.api_test_returns import IS_MOCK_TESTING


cost_router = APIRouter()
async def get_artifact_cost() -> ArtifactCostAnalyzer:
    return ArtifactCostAnalyzer()


@cost_router.get("/artifact/{artifact_type}/{id}/cost", status_code=status.HTTP_200_OK)
async def rate_model(
        id: str,
        artifact_type: str,
        dependency: bool,
        cost_analyzer: Annotated[ArtifactCostAnalyzer, Depends(get_artifact_cost)],
) -> ArtifactCost | None:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: ModelRaterEnum
    return_content: ArtifactCost

    return_code, return_content = await cost_analyzer.get_artifact_cost(artifact_type_model, id_model)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.NOT_FOUND:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")
        case return_code.INTERNAL_ERROR:
            raise HTTPException(status_code=return_code.value, detail="The artifact cost calculator encountered an error.")
    return None