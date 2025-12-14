from typing import List

from fastapi import APIRouter, HTTPException, status, Response, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import logging

from src.contracts.artifact_contracts import (
    ArtifactID,
    ArtifactType,
    ArtifactQuery,
    Artifact,
    ArtifactMetadata,
    ArtifactName,
    ArtifactRegEx,
    ArtifactData,
)
from ..global_state import artifact_accessor, global_config, cache_accessor
from ..model.artifact_accessor.enums import (
    GetArtifactsEnum,
    GetArtifactEnum,
    RegisterArtifactEnum,
    UpdateArtifactEnum,
)

accessor_router = APIRouter()


logger = logging.getLogger(__name__)


@accessor_router.post("/artifacts", status_code=status.HTTP_200_OK)
async def get_artifacts(
    response: Response,
    body: List[ArtifactQuery],
    offset: str = Query("0", pattern=r"^\d+$"),
) -> List[ArtifactMetadata]:
    return_code: GetArtifactsEnum
    return_content: list[ArtifactMetadata]

    response_agg: list[ArtifactMetadata] = []

    for request in body:
        return_code, return_content = artifact_accessor.get_artifacts(request, offset)

        match return_code:
            case return_code.SUCCESS:
                logger.info(
                    f"Successfully got page {offset} of artifacts, len {len(return_content)}"
                )
                response_agg.extend(return_content)
            case return_code.TOO_MANY_ARTIFACTS:
                logger.warning("Too many artifacts returned.")
                raise HTTPException(
                    status_code=return_code.value, detail="Too many artifacts returned."
                )

    response.headers["offset"] = str(int(offset) + len(return_content))
    return response_agg


@accessor_router.post("/artifact/byName/{name:path}", status_code=status.HTTP_200_OK)
async def get_artifacts_by_name(
    name: str,
) -> List[ArtifactMetadata]:
    logger.info(f"getting by name {name}")
    try:
        name_model: ArtifactName = ArtifactName(name=name)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact name"])

    return_code: GetArtifactEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = artifact_accessor.get_artifact_by_name(name_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            logger.info(f"Artifacts found.")
            return return_content
        case GetArtifactEnum.DOES_NOT_EXIST:
            logger.error(f"No artifacts found.")
            raise HTTPException(
                status_code=return_code.value, detail="No such artifact."
            )


@accessor_router.post("/artifact/byRegEx", status_code=status.HTTP_200_OK)
async def get_artifacts_by_regex(
    regex: ArtifactRegEx,
) -> List[ArtifactMetadata]:
    logger.info(f"getting by regex {regex.regex}")
    return_code: GetArtifactEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = artifact_accessor.get_artifact_by_regex(regex)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            logger.info(f"Artifacts found.")
            return return_content
        case GetArtifactEnum.DOES_NOT_EXIST:
            logger.error(f"No artifacts found.")
            raise HTTPException(
                status_code=return_code.value,
                detail="No artifact found under this regex.",
            )


@accessor_router.get("/artifacts/{artifact_type}/{id}")
async def get_artifact(
    artifact_type: str,
    id: str,
) -> Artifact:
    logger.info(f"getting by id: {id}")
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(
            errors=[f"invalid artifact type or id, {id}, {artifact_type}"]
        )

    return_code: GetArtifactEnum
    return_content: Artifact

    return_code, return_content = artifact_accessor.get_artifact(
        artifact_type_model, id_model
    )

    match return_code:
        case GetArtifactEnum.SUCCESS:
            logger.info(f"Artifact {artifact_type}/{id} retrieved.")
            return return_content
        case GetArtifactEnum.DOES_NOT_EXIST:
            logger.error(f"Artifact {artifact_type}/{id} does not exist.")
            raise HTTPException(
                status_code=return_code.value, detail="Artifact does not exist."
            )


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

    return_code: UpdateArtifactEnum

    if not global_config.ingest_asynchronous:
        return_code = artifact_accessor.update_artifact(
            artifact_type_model, id_model, body
        )
    else:
        return_code = await artifact_accessor.update_artifact_deferred(
            artifact_type_model, id_model, body
        )

    match return_code:
        case UpdateArtifactEnum.SUCCESS:
            logger.info(f"Artifact {artifact_type}/{id} updated.")
            response.content = "version is updated."
        case UpdateArtifactEnum.DOES_NOT_EXIST:
            logger.error(f"Artifact {artifact_type}/{id} does not exist.")
            raise HTTPException(
                status_code=return_code.value, detail="Artifact does not exist."
            )
        case UpdateArtifactEnum.DISQUALIFIED:
            logger.error(f"Artifact {artifact_type}/{id} disqualified.")
            raise HTTPException(
                status_code=return_code.value, detail="Artifact is not updated."
            )
        case UpdateArtifactEnum.DEFERRED:
            logger.info(f"Artifact {artifact_type}/{id} deferred.")
            raise HTTPException(
                status_code=return_code.value, detail="Artifact deferred."
            )


@accessor_router.delete(
    "/artifacts/{artifact_type}/{id}", status_code=status.HTTP_200_OK
)
async def delete_artifact(
    artifact_type: str,
    id: str,
    response: Response,
) -> None:
    logger.info(f"deleting artifact {artifact_type}/{id}")
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type or id"])

    return_code: GetArtifactEnum

    return_code = artifact_accessor.delete_artifact(artifact_type_model, id_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            logger.info(f"Artifact {artifact_type}/{id} deleted.")
            response.content = "Artifact is deleted."
        case GetArtifactEnum.DOES_NOT_EXIST:
            logger.error(f"Artifact {artifact_type}/{id} does not exist.")
            raise HTTPException(
                status_code=return_code.value, detail="Artifact does not exist."
            )


@accessor_router.post("/artifact/{artifact_type}", status_code=status.HTTP_201_CREATED)
async def register_artifact(
    artifact_type: str, body: ArtifactData, response: Response
) -> Artifact | None:
    logger.info(f"registering url {body.url} of type {artifact_type}")
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact type"])

    return_code: RegisterArtifactEnum
    return_content: Artifact | None = None
    if not global_config.ingest_asynchronous:
        return_code, return_content = artifact_accessor.register_artifact(
            artifact_type_model, body
        )
    else:
        return_code = await artifact_accessor.register_artifact_deferred(
            artifact_type_model, body
        )

    match return_code:
        case return_code.SUCCESS:
            logger.info(
                f"Register complete for url {body.url} of type {artifact_type}."
            )
            return return_content
        case return_code.ALREADY_EXISTS:
            logger.error(
                f"FAILED: url: {body.url} artifact_type {artifact_type} already exists"
            )
            raise HTTPException(
                status_code=return_code.value,
                detail="Authentication failed due to invalid or missing AuthenticationToken.",
            )
        case return_code.DISQUALIFIED:
            logger.error(
                f"FAILED: url: {body.url} artifact_type {artifact_type} disqualified"
            )
            raise HTTPException(
                status_code=return_code.value,
                detail="Artifact is not registered due to the disqualified rating.",
            )
        case return_code.BAD_REQUEST:
            logger.error(
                f"FAILED: url: {body.url} artifact_type {artifact_type} bad request"
            )
            raise HTTPException(status_code=return_code.value)
        case return_code.DEFERRED:
            logger.info(
                f"FAILED: url: {body.url} artifact_type {artifact_type} deferred"
            )
            response.status_code = return_code.value
        case return_code.INTERNAL_ERROR:
            logger.error(
                f"FAILED: url: {body.url} artifact_type {artifact_type} internal error during ingest"
            )
            raise HTTPException(status_code=return_code.value)
