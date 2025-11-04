from fastapi import Depends, APIRouter, HTTPException, status, Response, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from typing import Annotated

from src.model.external_contracts import ArtifactID, ArtifactType, ArtifactQuery, Artifact, ArtifactMetadata, ArtifactName, ArtifactRegEx, ArtifactData
from src.model.artifact_accessor import ArtifactAccessor, GetArtifactsEnum, GetArtifactEnum, RegisterArtifactEnum
from src.frontend_controller.authentication.auth_object import AccessLevel, access_level, VerifyAuth, AuthClass, \
    auth_class
from src.api_test_returns import IS_MOCK_TESTING

accessor_router = APIRouter()
async def artifact_accessor() -> ArtifactAccessor:
    return ArtifactAccessor()


@accessor_router.post("/artifacts", status_code=status.HTTP_200_OK)
async def get_artifacts(
        response: Response,
        body: ArtifactQuery,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        offset: str = Query(..., pattern=r"^\d+$"),
) -> list[ArtifactMetadata] | None:
    return_code: GetArtifactsEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = accessor.get_artifacts(body, offset)

    match return_code:
        case return_code.SUCCESS:
            response.headers["offset"] = str(int(offset) + 1)
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.TOO_MANY_ARTIFACTS:
            raise HTTPException(status_code=return_code.value, detail="Too many artifacts returned.")
    return None


@accessor_router.post("/artifact/byName/{name}", status_code=status.HTTP_200_OK)
async def get_artifacts_by_name(
        name: str,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
) -> list[ArtifactMetadata]:
    try:
        name_model: ArtifactName = ArtifactName(name=name)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: GetArtifactEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = accessor.get_artifact_by_name(name_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            return return_content
        case GetArtifactEnum.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="No such artifact.")


@accessor_router.post("/artifact/byRegEx", status_code=status.HTTP_200_OK)
async def get_artifacts_by_regex(
        regex: ArtifactRegEx,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
) -> list[ArtifactMetadata]:
    return_code: GetArtifactEnum
    return_content: list[ArtifactMetadata]

    return_code, return_content = accessor.get_artifact_by_regex(regex)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            return return_content
        case GetArtifactEnum.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="No artifact found under this regex.")


@accessor_router.get("/artifacts/{artifact_type}/{id}")
async def get_artifact(
        artifact_type: str,
        id: str,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
) -> Artifact:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: GetArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.get_artifact(artifact_type_model, id_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            return return_content
        case GetArtifactEnum.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@accessor_router.put("/artifacts/{artifact_type}/{id}", status_code=status.HTTP_200_OK)
async def update_artifact(
        artifact_type: str,
        id: str,
        body: Artifact,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
) -> None:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.update_artifact(artifact_type_model, id_model, body)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            response.content = "version is updated."
        case GetArtifactEnum.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")
    return None


@accessor_router.delete("/artifacts/{artifact_type}/{id}", status_code=status.HTTP_200_OK)
async def delete_artifact(
        artifact_type: str,
        id: str,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
) -> None:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.delete_artifact(artifact_type_model, id_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            response.content = "Artifact is deleted."
        case GetArtifactEnum.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case GetArtifactEnum.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@accessor_router.post("/artifacts/{artifact_type}", status_code=status.HTTP_201_CREATED)
async def register_artifact(
        artifact_type: str,
        body: ArtifactData,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
) -> Artifact:
    try:
        artifact_type_model: ArtifactType = ArtifactType(artifact_type)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: RegisterArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.register_artifact(artifact_type_model, body)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.ALREADY_EXISTS:
            raise HTTPException(status_code=return_code.value,
                                detail="Authentication failed due to invalid or missing AuthenticationToken.")
        case return_code.DISQUALIFIED:
            raise HTTPException(status_code=return_code.value,
                                detail="Artifact is not registered due to the disqualified rating.")