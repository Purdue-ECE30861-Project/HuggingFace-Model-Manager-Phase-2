from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError
from sqlalchemy.orm import dependency

from src.contracts.artifact_contracts import ArtifactID, ArtifactType, ArtifactCost
from ..global_state import database_manager


cost_router = APIRouter()


@cost_router.get("/artifact/{artifact_type}/{id}/cost", status_code=status.HTTP_200_OK)
async def cost_model(
        id: str,
        artifact_type: str,
        dependency: bool,
) -> ArtifactCost:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type or id"])

    if not database_manager.router_artifact.db_artifact_exists(id, artifact_type_model):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")

    return_content: ArtifactCost = database_manager.router_cost.db_artifact_cost(id, artifact_type_model, dependency)

    if not return_content:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal cost calculatioin error")
    return return_content