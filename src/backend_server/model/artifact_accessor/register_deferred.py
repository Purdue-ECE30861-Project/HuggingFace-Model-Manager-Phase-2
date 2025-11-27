import logging
import queue
from tempfile import TemporaryDirectory

from src.backend_server.model.artifact_accessor.enums import RegisterArtifactEnum
from src.backend_server.model.artifact_accessor.register_direct import artifact_and_rating_direct, register_data_store
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


def rater_task(artifact_type: ArtifactType, body: ArtifactData, processes: int, ingest_score_threshold: float, s3_manager: S3BucketManager, db_manager: DBManager):
    artifact_id: str = generate_unique_id(body.url)
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

        new_artifact, rating = artifact_and_rating_direct(temp_path, body, artifact_type, processes)

        if rating.net_score < ingest_score_threshold:
            logger.error(f"FAILED: {body.url} id {artifact_id} failed to ingest due to low score")
            return RegisterArtifactEnum.DISQUALIFIED, None

        result = register_data_store(s3_manager, db_manager, new_artifact, size, rating, temp_path)

class RaterTaskManager:
    def __init__(self, ingest_score_threshold: float, s3_manager: S3BucketManager, db_manager: DBManager, max_workers: int = 4, max_processes_per_rater: int = 1, max_queue_size: int = 100):
        self.max_processes_per_rater: int = max_processes_per_rater
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        self.queue: asyncio.Queue[tuple[ArtifactType, ArtifactData]] = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._dispatcher = None

        self._ingest_score_threshold = ingest_score_threshold
        self._s3_manager = s3_manager
        self._db_manager = db_manager

    async def start(self):
        self._running = True
        self._dispatcher = asyncio.create_task(self._dispatch_loop())

    async def _dispatch_loop(self):
        while self._running:
            artifact_type, body = await self.queue.get()
            asyncio.get_event_loop().run_in_executor(
                self.executor, rater_task, artifact_type, body, self.max_processes_per_rater, self._ingest_score_threshold, self._s3_manager, self._db_manager
            )

    async def submit(self, artifact_type: ArtifactType, body: ArtifactData) -> bool:
        try:
            await self.queue.put((artifact_type, body))
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
