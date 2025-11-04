from fastapi import Depends, APIRouter, HTTPException, status, Response
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError

from src.model.external_contracts import ArtifactID, ArtifactLineageGraph
from src.model.artifact_lineage import LineageGraphAnalyzer, LineageEnum
from src.frontend_controller.authentication.auth_object import AccessLevel, access_level, VerifyAuth
from src.api_test_returns import IS_MOCK_TESTING


lineage_router = APIRouter()
async def get_artifact_lineage_graph() -> LineageGraphAnalyzer:
    return LineageGraphAnalyzer()


@lineage_router.get("/artifact/model/{id}/lineage", status_code=status.HTTP_200_OK)
async def get_model_lineage(
        id: str,
        lineage_analyzer: Annotated[LineageGraphAnalyzer, Depends(get_artifact_lineage_graph)],
) -> ArtifactLineageGraph | None:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: LineageEnum
    return_content: ArtifactLineageGraph

    return_code, return_content = await lineage_analyzer.get_lineage_graph(id_model)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.MALFORMED:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")
    return None