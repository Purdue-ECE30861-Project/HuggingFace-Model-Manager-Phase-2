from fastapi import Depends, APIRouter, HTTPException, status, Response
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError

from src.model.external_contracts import ArtifactID, ModelRating
from src.model.model_rater import ModelRater, ModelRaterEnum
from src.frontend_controller.authentication.auth_object import AccessLevel, access_level, VerifyAuth
from src.api_test_returns import IS_MOCK_TESTING


rater_router = APIRouter()
async def model_rater() -> ModelRater:
    return ModelRater()


@rater_router.get("/artifact/model/{id}/rate", status_code=status.HTTP_200_OK)
async def rate_model(
        id: str,
        rater: Annotated[ModelRater, Depends(model_rater)]
) -> ModelRating | None:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["internal"])

    return_code: ModelRaterEnum
    return_content: ModelRating

    return_code, return_content = await rater.rate_model(id_model)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.NOT_FOUND:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")
        case return_code.INTERNAL_ERROR:
            raise HTTPException(status_code=return_code.value, detail="The artifact rating system encountered an error while computing at least one metric.")
    return None