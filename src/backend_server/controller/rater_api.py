from fastapi import Depends, APIRouter, HTTPException, status, Response
from fastapi.exceptions import RequestValidationError
from typing import Annotated
from pydantic import ValidationError

from src.external_contracts import ArtifactID, ModelRating
from ..model.model_rater import ModelRater, ModelRaterEnum


rater_router = APIRouter()


@rater_router.get("/artifact/model/{id}/rate", status_code=status.HTTP_200_OK)
async def rate_model(
        id: str,
        rater: Annotated[ModelRater, Depends(ModelRater)]
) -> ModelRating:
    try:
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact id"])

    return_code: ModelRaterEnum
    return_content: ModelRating

    return_code, return_content = await rater.rate_model(id_model)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.NOT_FOUND:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")
        case return_code.INTERNAL_ERROR:
            raise HTTPException(status_code=return_code.value, detail="The artifact rating system encountered an error while computing at least one metric.")