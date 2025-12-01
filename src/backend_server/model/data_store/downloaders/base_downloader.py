import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from src.contracts.artifact_contracts import ArtifactType


class BaseArtifactDownloader(ABC):
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    @abstractmethod
    def download_artifact(self, url: str, artifact_type: ArtifactType, tempdir: Path) -> float:
        raise NotImplementedError()


def extract_name_from_url(url: str, artifact_type: ArtifactType) -> str:
    return "GoobyGoober" # implement me later

def generate_unique_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()