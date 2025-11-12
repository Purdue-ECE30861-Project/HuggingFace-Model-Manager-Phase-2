from enum import Enum
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from atasker import task_supervisor, background_task

from pydantic import validate_call

from src.contracts.model_rating import ModelRating, Artifact


class ModelRaterEnum(Enum):
    SUCCESS = 200
    NOT_FOUND = 404
    INTERNAL_ERROR = 500
class ModelRater:
    @validate_call
    async def rate_model(self, artifact: Artifact) -> tuple[ModelRaterEnum, ModelRating]:
        raise NotImplementedError()

    async def rate_model_ingest(self, path: TemporaryDirectory) -> tuple[ModelRaterEnum, ModelRating]:
        raise NotImplementedError()