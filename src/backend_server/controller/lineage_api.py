from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError
import logging
from src.backend_server.global_state import database_manager
from src.contracts.artifact_contracts import ArtifactID, ArtifactLineageGraph


lineage_router = APIRouter()
logger = logging.getLogger(__name__)


@lineage_router.get("/artifact/model/{id}/lineage", status_code=status.HTTP_200_OK)
async def get_model_lineage(
        id: str,
) -> ArtifactLineageGraph:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact id"])

    return_content: None|ArtifactLineageGraph = database_manager.router_lineage.db_artifact_lineage(id)

    if not return_content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
    return return_content