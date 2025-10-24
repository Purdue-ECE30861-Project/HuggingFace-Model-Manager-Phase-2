from importlib.resources import contents
from unittest import case

from fastapi import FastAPI, Header, Query, Path, Body, status, Depends, Response, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, RootModel, validate_call
from typing import Annotated, Callable, Awaitable
from enum import Enum
import re

from api_types import *


app = FastAPI()
ENFORCING_AUTHENTICATION: bool = False


class AccessLevel(Enum):
    NO_AUTHENTICATION = 0,
    USER_AUTHENTICATION = 1,
    ADMIN_AUTHENTICATION = 2


def access_level(level: AccessLevel):
    def decorator(func):
        setattr(func, "access_level", level)
        return func
    return decorator


class AuthenticatorReturn(Enum):
    OK = 0,
    BAD_TOKEN = 1,
    BAD_AUTHENTICATION = 2


class Authenticator:
    @validate_call
    def __init__(self, request: Request):
        self.level: AccessLevel = getattr(request.scope["route"].endpoint, "access_level", "public")

    @validate_call
    def check_authentication(self, x_authorization: str) -> AccessLevel:
        return AccessLevel.NO_AUTHENTICATION

    @validate_call
    async def authenticate(self, x_authorization: str | None) -> AuthenticatorReturn:
        if not ENFORCING_AUTHENTICATION:
            return AuthenticatorReturn.OK
        elif not x_authorization:
            return AuthenticatorReturn.BAD_TOKEN
        elif self.check_authentication(x_authorization).value < self.level.value:
            return AuthenticatorReturn.BAD_AUTHENTICATION
        return AuthenticatorReturn.BAD_TOKEN

    @validate_call
    async def authenticate_to_artifact(self, id: ArtifactID, x_authorization: str | None) -> AuthenticatorReturn:
        return AuthenticatorReturn.OK


class AuthClass(Enum):
    AUTH_STANDARD = 0,
    AUTH_ARTIFACT = 1
class VerifyAuth:
    def __init__(self, bad_permissions_message: str = "Not Authorized for Operation", auth_class: AuthClass = AuthClass.AUTH_STANDARD):
        self.bad_permissions_message: str = bad_permissions_message
        self.auth_class: AuthClass = auth_class

    async def special_auth(self, x_authorization: str | None, request: Request, authenticator: Authenticator) -> AuthenticatorReturn:
        match self.auth_class:
            case AuthClass.AUTH_STANDARD:
                return AuthenticatorReturn.OK
            case AuthClass.AUTH_ARTIFACT:
                return await authenticator.authenticate_to_artifact(x_authorization, request.path_params["id"])

    async def __call__(self, request: Request, x_authorization: str | None = Header(None, alias="X-Authorization")):
        authenticator: Authenticator = Authenticator(request)
        match await authenticator.authenticate(x_authorization):
            case AuthenticatorReturn.OK:
                return self.special_auth(x_authorization, request, authenticator)
            case AuthenticatorReturn.BAD_TOKEN:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=self.bad_permissions_message)
            case AuthenticatorReturn.BAD_AUTHENTICATION:
                raise HTTPException(status_code=403, detail="Authentication failed due to invalid or missing AuthenticationToken.")



VALIDATION_ERROR_MESSAGE_LOOKUP: dict[tuple[str, str], str] = {
    ("POST", "/artifacts"):"There is missing field(s) in the artifact_query or it is formed improperly, or is invalid.",
    ("GET", "/artifacts/*/*"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid.",
    ("DELETE", "/artifacts/*/*"):"There is missing field(s) in the artifact_type or artifact_id or invalid",
    ("PUT", "/artifact/*/*"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid.",
    ("GET", "/artifact/model/*/rate"):"There is missing field(s) in the artifact_id or it is formed improperly, or is invalid.",
    ("POST", "/artifact/*"):"There is missing field(s) in the artifact_data or it is formed improperly (must include a single url)."
}

def get_validation_error_message(key: tuple[str, str]) -> str:
    exact_match = VALIDATION_ERROR_MESSAGE_LOOKUP.get(key)
    if exact_match is not None:
        return exact_match
    for (m, p), message in VALIDATION_ERROR_MESSAGE_LOOKUP.items():
        if m != key[0]:
            continue
        # Convert wildcard '*' to regex
        pattern = "^" + re.escape(p).replace("\\*", "[^/]+") + "$"
        if re.match(pattern, key[1]):
            return message

    return "Bad Format"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    raise HTTPException(
        status_code=400,
        detail=VALIDATION_ERROR_MESSAGE_LOOKUP[(request.method, request.url.path)],
    )


class GetArtifactsEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    TOO_MANY_ARTIFACTS = 413

class GetArtifactEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    DOES_NOT_EXIST = 404

class RegisterArtifactEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    ALREADY_EXISTS = 409
    DISQUALIFIED = 424

class ArtifactAccessor:
    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        raise NotImplementedError()

    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact]:
        raise NotImplementedError()

    @validate_call
    def update_artifact(self, artifact_type: ArtifactType, id: ArtifactID, body: Artifact) -> tuple[GetArtifactEnum, None]:
        raise NotImplementedError()

    @validate_call
    def delete_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact]:
        raise NotImplementedError()

    @validate_call
    def register_artifact(self, artifact_type: ArtifactType, body: ArtifactData) -> tuple[RegisterArtifactEnum, Artifact]:
        raise NotImplementedError()


async def artifact_accessor() -> ArtifactAccessor:
    return ArtifactAccessor()

@access_level(AccessLevel.NO_AUTHENTICATION)
@app.post("/artifacts", status_code = status.HTTP_200_OK)
async def get_artifacts(
        response: Response,
        body: ArtifactQuery,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        offset: str = Query(..., pattern=r"^\d+$"),
        x_authorization: str = Depends(VerifyAuth())
) -> List[ArtifactMetadata] | None:
    return_code: GetArtifactsEnum
    return_content: List[ArtifactMetadata]

    return_code, return_content = accessor.get_artifacts(body, offset)

    match return_code:
        case return_code.SUCCESS:
            response.headers["offset"] = str(int(offset) + 1)
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.TOO_MANY_ARTIFACTS:
            raise HTTPException(status_code=return_code.value, detail="Too many artifacts returned.")


async def reset_registry():
    pass

@access_level(AccessLevel.ADMIN_AUTHENTICATION)
@app.delete("/reset", status_code = status.HTTP_200_OK)
async def reset(response: Response, x_authorization: str = Depends(VerifyAuth(bad_permissions_message="You do not have permission to reset the registry."))):
    response.body = "Registry is reset."


@access_level(AccessLevel.NO_AUTHENTICATION)
@app.get("/artifacts/{artifact_type}/{id}")
async def get_artifact(
        artifact_type: ArtifactType,
        id: ArtifactID,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth())
) -> Artifact | None:
    return_code: GetArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.get_artifact(artifact_type, id)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@access_level(AccessLevel.USER_AUTHENTICATION)
@app.put("/artifacts/{artifact_type}/{id}", status_code = status.HTTP_200_OK)
async def update_artifact(
        artifact_type: ArtifactType,
        id: ArtifactID,
        body: Artifact,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth(auth_class=AuthClass.AUTH_ARTIFACT))
) -> None:
    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.update_artifact(artifact_type, id, body)

    match return_code:
        case return_code.SUCCESS:
            response.content = "version is updated."
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@access_level(AccessLevel.USER_AUTHENTICATION)
@app.delete("/artifacts/{artifact_type}/{id}", status_code = status.HTTP_200_OK)
async def delete_artifact(
        artifact_type: ArtifactType,
        id: ArtifactID,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth(auth_class=AuthClass.AUTH_ARTIFACT))
) -> None:
    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.delete_artifact(artifact_type, id)

    match return_code:
        case return_code.SUCCESS:
            response.content = "Artifact is deleted."
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@access_level(AccessLevel.USER_AUTHENTICATION)
@app.post("/artifacts/{artifact_type}", status_code = status.HTTP_201_CREATED)
async def register_artifact(
        artifact_type: ArtifactType,
        body: ArtifactData,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth())
) -> Artifact | None:
    return_code: RegisterArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.register_artifact(artifact_type, body)
    
    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.ALREADY_EXISTS:
            raise HTTPException(status_code=return_code.value, detail="Authentication failed due to invalid or missing AuthenticationToken.")
        case return_code.DISQUALIFIED:
            raise HTTPException(status_code=return_code.value, detail="Artifact is not registered due to the disqualified rating.")


class ModelRaterEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    NOT_FOUND = 404
    INTERNAL_ERROR = 500


class ModelRater:
    @validate_call
    async def rate_model(self, id: ArtifactID) -> tuple[ModelRaterEnum, ModelRating]:
        raise NotImplementedError()


async def artifact_rater() -> ModelRater:
    return ModelRater()

@access_level(AccessLevel.USER_AUTHENTICATION)
@app.get("/artifact/model/{id}/rate", status_code=status.HTTP_200_OK)
async def rate_model(
        id: ArtifactID,
        response: Response,
        rater: Annotated[ModelRater, Depends(artifact_rater)],
        x_authorization: str = Depends(VerifyAuth()),
):
    return_code: ModelRaterEnum
    return_content: ModelRating

    return_code, return_content = await rater.rate_model(id)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.NOT_FOUND:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")
        case return_code.INTERNAL_ERROR:
            raise HTTPException(status_code=return_code.value, detail="The artifact rating system encountered an error while computing at least one metric.")
