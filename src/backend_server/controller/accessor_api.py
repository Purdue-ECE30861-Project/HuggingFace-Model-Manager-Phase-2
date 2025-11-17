from fastapi import Depends, APIRouter, HTTPException, status, Response, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from typing import Annotated, List

from src.contracts.artifact_contracts import ArtifactID, ArtifactType, ArtifactQuery, Artifact, ArtifactMetadata, ArtifactName, ArtifactRegEx, ArtifactData
from ..model.artifact_accessor.artifact_accessor import ArtifactAccessor, GetArtifactsEnum, GetArtifactEnum, RegisterArtifactEnum
from ..model.artifact_accessor.register_deferred import RaterTaskManager
from ..global_state import artifact_accessor as accessor
from ...contracts.auth_contracts import ArtifactAuditEntry

accessor_router = APIRouter()


@accessor_router.post("/artifacts", status_code=status.HTTP_200_OK)
async def get_artifacts(
        response: Response,
        body: ArtifactQuery,
        offset: str = Query(..., pattern=r"^\d+$"),
) -> List[ArtifactMetadata]:
    return_code: GetArtifactsEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = accessor.get_artifacts(body, offset)

    match return_code:
        case return_code.SUCCESS:
            response.headers["offset"] = str(int(offset) + 1)
            return return_content
        case return_code.TOO_MANY_ARTIFACTS:
            raise HTTPException(status_code=return_code.value, detail="Too many artifacts returned.")


@accessor_router.post("/artifact/byName/{name}", status_code=status.HTTP_200_OK)
async def get_artifacts_by_name(
        name: str,
) -> List[ArtifactMetadata]:
    try:
        name_model: ArtifactName = ArtifactName(name=name)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact name"])

    return_code: GetArtifactEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = accessor.get_artifact_by_name(name_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            return return_content
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="No such artifact.")


@accessor_router.post("/artifact/byRegEx", status_code=status.HTTP_200_OK)
async def get_artifacts_by_regex(
        regex: ArtifactRegEx,
) -> List[ArtifactMetadata]:
    return_code: GetArtifactEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = accessor.get_artifact_by_regex(regex)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            return return_content
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="No artifact found under this regex.")


@accessor_router.get("/artifacts/{artifact_type}/{id}")
async def get_artifact(
        artifact_type: str,
        id: str,
) -> Artifact:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type or id"])

    return_code: GetArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.get_artifact(artifact_type_model, id_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            return return_content
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@accessor_router.put("/artifacts/{artifact_type}/{id}", status_code=status.HTTP_200_OK)
async def update_artifact(
        artifact_type: str,
        id: str,
        body: Artifact,
        response: Response,
) -> None:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type or id"])

    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.update_artifact(artifact_type_model, id_model, body)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            response.content = "version is updated."
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@accessor_router.delete("/artifacts/{artifact_type}/{id}", status_code=status.HTTP_200_OK)
async def delete_artifact(
        artifact_type: str,
        id: str,
        response: Response,
) -> None:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type or id"])

    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.delete_artifact(artifact_type_model, id_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            response.content = "Artifact is deleted."
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@accessor_router.post("/artifacts/{artifact_type}", status_code=status.HTTP_201_CREATED)
async def register_artifact(
        artifact_type: str,
        body: ArtifactData,
        response: Response
) -> Artifact | None:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type"])

    return_code: RegisterArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.register_artifact(artifact_type_model, body)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.ALREADY_EXISTS:
            raise HTTPException(status_code=return_code.value,
                                detail="Authentication failed due to invalid or missing AuthenticationToken.")
        case return_code.DISQUALIFIED:
            raise HTTPException(status_code=return_code.value,
                                detail="Artifact is not registered due to the disqualified rating.")
        case return_code.BAD_REQUEST:
            raise HTTPException(status_code=return_code.value)
        case return_code.DEFERRED:
            response.status_code = 202


@accessor_router.get("/artifact/{artifact_type}/{id}/audit")
async def get_audit_history(
    artifact_type: str,
    id: str,
) -> List[ArtifactAuditEntry]:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type"])

