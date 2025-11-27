from fastapi import Depends, APIRouter, HTTPException, status, Response, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from typing import Annotated, List

from src.contracts.artifact_contracts import ArtifactID, ArtifactType, ArtifactQuery, Artifact, ArtifactMetadata, ArtifactName, ArtifactRegEx, ArtifactData
from ..model.artifact_accessor.artifact_accessor import ArtifactAccessor, GetArtifactsEnum, GetArtifactEnum, RegisterArtifactEnum
from ..model.artifact_accessor.register_deferred import RaterTaskManager
from ..global_state import artifact_accessor as accessor
from ..global_state import database_manager
from ...contracts.auth_contracts import ArtifactAuditEntry

audit_router = APIRouter()


@audit_router.get("/artifact/{artifact_type}/{id}/audit")
async def get_audit_history(
    artifact_type: str,
    id: str,
) -> List[ArtifactAuditEntry]:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type"])

    if not database_manager.router_artifact.db_artifact_exists(id, artifact_type_model):
        raise HTTPException(status_code=404, detail="artifact not found")

    audit_results = database_manager.router_audit.db_artifact_audit(artifact_type_model, id)
    if not audit_results:
        return []
    return audit_results
