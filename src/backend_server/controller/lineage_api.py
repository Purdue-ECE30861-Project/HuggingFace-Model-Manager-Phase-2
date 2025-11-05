from fastapi import Depends, APIRouter, HTTPException, status, Response
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError

from src.external_contracts import ArtifactID, ArtifactLineageGraph
from ..model.artifact_lineage import LineageGraphAnalyzer, LineageEnum


lineage_router = APIRouter()
async def get_artifact_lineage_graph() -> LineageGraphAnalyzer:
    return LineageGraphAnalyzer()


@lineage_router.get("/artifact/model/{id}/lineage", status_code=status.HTTP_200_OK)
async def get_model_lineage(
        id: str,
        lineage_analyzer: Annotated[LineageGraphAnalyzer, Depends(get_artifact_lineage_graph)],
) -> ArtifactLineageGraph:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact id"])

    return_code: LineageEnum
    return_content: ArtifactLineageGraph

    return_code, return_content = await lineage_analyzer.get_lineage_graph(id_model)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")