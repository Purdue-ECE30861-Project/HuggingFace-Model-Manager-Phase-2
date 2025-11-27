from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError

from src.backend_server.global_state import database_manager
from src.contracts.artifact_contracts import ArtifactID
from src.contracts.model_rating import ModelRating


rater_router = APIRouter()


@rater_router.get("/artifact/model/{id}/rate", status_code=status.HTTP_200_OK)
async def rate_model(
        id: str,
) -> ModelRating:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact id"])

    if not database_manager.router_artifact.db_artifact_exists(id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")

    return_content: None|ModelRating = database_manager.router_rating.db_rating_get(id)
    if not return_content:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="rating internal error")

    return return_content