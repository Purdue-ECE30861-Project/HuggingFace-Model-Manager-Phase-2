from pydantic import validate_call
from enum import Enum
from src.external_contracts import ArtifactID, ModelRating


class ModelRaterEnum(Enum):
    SUCCESS = 200
    NOT_FOUND = 404
    INTERNAL_ERROR = 500
class ModelRater:
    @validate_call
    async def rate_model(self, id: ArtifactID) -> tuple[ModelRaterEnum, ModelRating]:
        raise NotImplementedError()