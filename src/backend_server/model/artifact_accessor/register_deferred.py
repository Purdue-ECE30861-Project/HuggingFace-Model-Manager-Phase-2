import logging
import queue
from tempfile import TemporaryDirectory

from src.backend_server.model.artifact_accessor.dependencies import ArtifactAccessorDependencies
from src.backend_server.model.artifact_accessor.enums import RegisterArtifactEnum, UpdateArtifactEnum
from src.backend_server.model.artifact_accessor.register_direct import \
    register_data_store_model, register_data_store_artifact, update_data_store_model, update_data_store_artifact
from src.backend_server.model.data_store.database_connectors.mother_db_connector import DBManager
from src.backend_server.model.data_store.downloaders.base_downloader import BaseArtifactDownloader, generate_unique_id
from src.backend_server.model.data_store.downloaders.gh_downloader import GHArtifactDownloader
from src.backend_server.model.data_store.downloaders.hf_downloader import HFArtifactDownloader
from src.backend_server.model.data_store.s3_manager import S3BucketManager
from src.contracts.model_rating import ModelRating
import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import contextlib

from src.contracts.artifact_contracts import Artifact, ArtifactType, ArtifactData


logger = logging.getLogger(__name__)


def register_task(artifact_id: str, artifact_type: ArtifactType, body: ArtifactData, dependencies: ArtifactAccessorDependencies):
    temporary_downloader: BaseArtifactDownloader = HFArtifactDownloader()
    if artifact_type == ArtifactType.code:
        temporary_downloader = GHArtifactDownloader()

    with TemporaryDirectory() as tempdir:
        size: float = 0.0
        temp_path: Path = Path(tempdir)
        try:
            size = temporary_downloader.download_artifact(body.url, artifact_type, temp_path)

        except FileNotFoundError:
            logger.error(f"FAILED: model not found for {body.url}")
            return RegisterArtifactEnum.BAD_REQUEST, None
        except (OSError, EnvironmentError):
            logger.error(f"FAILED: internal error when downloading artifact")
            return RegisterArtifactEnum.DISQUALIFIED, None

        if artifact_type == ArtifactType.model:
            register_data_store_model(artifact_id, body, size, temp_path, dependencies)
        else:
            register_data_store_artifact(artifact_id, body, artifact_type, size, temp_path, dependencies)

def update_task(artifact_id: str, artifact_type: ArtifactType, body: Artifact, dependencies: ArtifactAccessorDependencies):
    temporary_downloader: BaseArtifactDownloader = HFArtifactDownloader()
    if artifact_type == ArtifactType.code:
        temporary_downloader = GHArtifactDownloader()

    with TemporaryDirectory() as tempdir:
        size: float = 0.0
        temp_path: Path = Path(tempdir)
        try:
            size = temporary_downloader.download_artifact(body.url, artifact_type, temp_path)
        except FileNotFoundError:
            logger.error(f"FAILED: model not found for {body.url}")
            return UpdateArtifactEnum.DISQUALIFIED
        except (OSError, EnvironmentError):
            logger.error(f"FAILED: internal error when downloading artifact")
            return UpdateArtifactEnum.DISQUALIFIED

        update_result: UpdateArtifactEnum
        if artifact_type == ArtifactType.model:
            artifact, readme, names, rating = dependencies.db.db_get_snapshot_model(artifact_id)
            update_result = update_data_store_model(body, size, temp_path, dependencies)
            if update_result != UpdateArtifactEnum.SUCCESS:
                dependencies.db.db_restore_snapshot_model(artifact, readme, names, rating)

        else:
            update_result = update_data_store_artifact(body, size, temp_path, dependencies)

class RaterTaskManager:
    def __init__(self, ingest_score_threshold: float, s3_manager: S3BucketManager, db_manager: DBManager, max_workers: int = 4, max_processes_per_rater: int = 1, max_queue_size: int = 100):
        self.max_processes_per_rater: int = max_processes_per_rater
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        self.queue: asyncio.Queue[tuple[str, ArtifactType, ArtifactData | Artifact]] = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._dispatcher = None

        self.dependencies: ArtifactAccessorDependencies = ArtifactAccessorDependencies(
            ingest_score_threshold=ingest_score_threshold,
            s3=s3_manager,
            db=db_manager,
            num_processors=self.max_processes_per_rater,
        )

    async def start(self):
        self._running = True
        self._dispatcher = asyncio.create_task(self._dispatch_loop())

    async def _dispatch_loop(self):
        while self._running:
            artifact_id, artifact_type, body = await self.queue.get()
            if isinstance(body, Artifact):
                asyncio.get_event_loop().run_in_executor(
                    self.executor, update_task, artifact_id, artifact_type, body, self.dependencies
                )
            else:
                asyncio.get_event_loop().run_in_executor(
                    self.executor, register_task, artifact_id, artifact_type, body, self.dependencies
                )

    async def submit(self, artifact_id: str, artifact_type: ArtifactType, body: ArtifactData) -> bool:
        try:
            await self.queue.put((artifact_id, artifact_type, body))
            return True
        except queue.Full:
            return False

    async def shutdown(self):
        self._running = False
        if self._dispatcher:
            self._dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher
        self.executor.shutdown(wait=True)
