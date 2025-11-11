from enum import Enum
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from atasker import task_supervisor, background_task

from pydantic import validate_call

from src.contracts.model_rating import ModelRating, Artifact


@background_task
def rater_task(artifact: Artifact, filepath: Path):
    pass


class ModelRatingQueue:
    def __init__(self, maxsize: int=0):
        self.queue: Queue = Queue()
        task_supervisor.set_thread_pool(pool_size=1)

    def submit_rater_job(self, artifact: Artifact, filepath: Path):
        pass

    @staticmethod
    def startup_rater_service(self):
        task_supervisor.start()

    @staticmethod
    def stop_rater_service(self):
        task_supervisor.stop()


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