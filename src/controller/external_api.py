from importlib.resources import contents
from unittest import case

from fastapi import FastAPI, Header, Query, Path, Body, status, Depends, Response, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, RootModel, validate_call
from typing import Annotated, Callable, Awaitable
from enum import Enum
import re

from external_contracts import *
from authentication.auth_object import Authenticator, AuthClass, AccessLevel, ENFORCING_AUTHENTICATION, AuthClass, access_level, VerifyAuth
from ..model.artifact_accessor import ArtifactAccessor, GetArtifactsEnum, RegisterArtifactEnum, artifact_accessor


app = FastAPI()


VALIDATION_ERROR_MESSAGE_LOOKUP: dict[tuple[str, str], str] = {
    ("POST", "/artifacts"):"There is missing field(s) in the artifact_query or it is formed improperly, or is invalid.",
    ("GET", "/artifacts/*/*"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid.",
    ("DELETE", "/artifacts/*/*"):"There is missing field(s) in the artifact_type or artifact_id or invalid",
    ("PUT", "/artifact/*/*"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid.",
    ("GET", "/artifact/model/*/rate"):"There is missing field(s) in the artifact_id or it is formed improperly, or is invalid.",
    ("POST", "/artifact/*"):"There is missing field(s) in the artifact_data or it is formed improperly (must include a single url).",
    ("GET", "/artifact/*/*/cost"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
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


class ModelRaterEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    NOT_FOUND = 404
    INTERNAL_ERROR = 500


class ModelRater:
    @validate_call
    async def rate_model(self, id: ArtifactID) -> tuple[ModelRaterEnum, ModelRating]:
        raise NotImplementedError()


async def model_rater() -> ModelRater:
    return ModelRater()

@access_level(AccessLevel.USER_AUTHENTICATION)
@app.get("/artifact/model/{id}/rate", status_code=status.HTTP_200_OK)
async def rate_model(
        id: ArtifactID,
        response: Response,
        rater: Annotated[ModelRater, Depends(model_rater)],
        x_authorization: str = Depends(VerifyAuth()),
) -> ModelRating | None:
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


class ArtifactCostAnalyzer:
    @validate_call
    async def get_artifact_cost(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[ModelRaterEnum, ArtifactCost]:
        raise NotImplementedError()


async def get_artifact_cost() -> ArtifactCostAnalyzer:
    return ArtifactCostAnalyzer()

@access_level(AccessLevel.USER_AUTHENTICATION)
@app.get("/artifact/{artifact_type}/{id}/cost", status_code=status.HTTP_200_OK)
async def rate_model(
        id: ArtifactID,
        artifact_type: ArtifactType,
        response: Response,
        cost_analyzer: Annotated[ArtifactCostAnalyzer, Depends(get_artifact_cost)],
        x_authorization: str = Depends(VerifyAuth()),
) -> ArtifactCost | None:
    return_code: ModelRaterEnum
    return_content: ArtifactCost

    return_code, return_content = await cost_analyzer.get_artifact_cost(artifact_type, id)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.NOT_FOUND:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")
        case return_code.INTERNAL_ERROR:
            raise HTTPException(status_code=return_code.value, detail="The artifact cost calculator encountered an error.")


class LineageEnum(Enum):
    SUCCESS = 200
    MALFORMED = 400
    DOES_NOT_EXIST = 404
class LineageGraphAnalyzer:
    @validate_call
    async def get_lineage_graph(self, id: ArtifactID) -> tuple[LineageEnum, ArtifactLineageGraph]:
        raise NotImplementedError()

async def get_artifact_lineage_graph() -> LineageGraphAnalyzer:
    return LineageGraphAnalyzer()


@access_level(AccessLevel.USER_AUTHENTICATION)
@app.get("/artifact/model/{id}/lineage", status_code=status.HTTP_200_OK)
async def get_model_lineage(
        id: ArtifactID,
        response: Response,
        lineage_analyzer: Annotated[LineageGraphAnalyzer, Depends(get_artifact_lineage_graph)],
        x_authorization: str = Depends(VerifyAuth()),
) -> ArtifactLineageGraph | None:
    return_code: LineageEnum
    return_content: ArtifactLineageGraph

    return_code, return_content = await lineage_analyzer.get_lineage_graph(id)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.MALFORMED:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


# TODO: LICENSE CHECK!
# TODO: TRACKS ENDPOINT!