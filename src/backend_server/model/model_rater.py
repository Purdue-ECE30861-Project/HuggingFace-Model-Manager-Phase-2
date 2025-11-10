from tempfile import TemporaryDirectory

from pydantic import validate_call
from enum import Enum
from src.external_contracts import ArtifactID, ModelRating, Artifact


class ModelRaterEnum(Enum):
    SUCCESS = 200
    NOT_FOUND = 404
    INTERNAL_ERROR = 500
class ModelRater:
    @validate_call
    async def rate_model(self, artifact: Artifact) -> tuple[ModelRaterEnum, ModelRating]:
        raise NotImplementedError()

    @validate_call
    async def rate_model_ingest(self, path: TemporaryDirectory) -> tuple[ModelRaterEnum, ModelRating]:
        raise NotImplementedError()