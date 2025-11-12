from src.contracts.model_rating import ModelRating
import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import contextlib

from src.contracts.artifact_contracts import Artifact


def rater_task(artifact: Artifact, filepath: Path, processes: int):
    return ModelRating.generate_rating(filepath, artifact, processes)

class RaterTaskManager:
    def __init__(self, max_workers: int = 4, max_processes_per_rater: int = 1):
        self.max_processes_per_rater: int = max_processes_per_rater
        self.executor = ProcessPoolExecutor(max_workers=max_workers)
        self.queue: asyncio.Queue[tuple[Artifact, Path]] = asyncio.Queue()
        self._running = False
        self._dispatcher = None

    async def start(self):
        self._running = True
        self._dispatcher = asyncio.create_task(self._dispatch_loop())

    async def _dispatch_loop(self):
        while self._running:
            artifact, filepath = await self.queue.get()
            asyncio.get_event_loop().run_in_executor(
                self.executor, rater_task, artifact, filepath, self.max_processes_per_rater
            )

    async def submit(self, artifact: Artifact, filepath: Path):
        await self.queue.put((artifact, filepath))

    async def shutdown(self):
        self._running = False
        if self._dispatcher:
            self._dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher
        self.executor.shutdown(wait=True)
