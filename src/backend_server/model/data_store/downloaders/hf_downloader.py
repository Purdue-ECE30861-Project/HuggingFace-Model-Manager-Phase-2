from typing import Optional

import huggingface_hub.utils
from huggingface_hub import snapshot_download
import os
import shutil
import tempfile

from src.external_contracts import ArtifactData, ArtifactType


class HFArtifactDownloader:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _validate_url(self, url: str) -> bool:
        """Internal method to validate URL format"""
        return url.startswith(('http://huggingface.co', 'https://huggingface.co'))

    def _get_repo_id_from_url(self, url: str, artifact_type: ArtifactType) -> str:
        split: list[str] = url.split("/")

        match artifact_type:
            case ArtifactType.model:
                return f"{split[3]}/{split[4]}"
            case ArtifactType.dataset:
                if split[3] != "datasets":
                    raise NameError("Specified type of dataset, hugginface url format requires 'dataset' path")
                return f"{split[4]}/{5}"
            case ArtifactType.code:
                raise TypeError("Cannot retrieve code from huggingface URL, specify github url")

    def _huggingface_pull(self, repo_id: str, tempdir: tempfile.TemporaryDirectory, artifact_type: ArtifactType):
        try:
            snapshot_download(repo_id=repo_id, local_dir=tempdir.name, repo_type="dataset") \
                if artifact_type == "model" else \
                snapshot_download(repo_id=repo_id, local_dir=tempdir.name)
        except (huggingface_hub.utils.RepositoryNotFoundError, huggingface_hub.utils.RevisionNotFoundError):
            raise FileNotFoundError("Requested repository doesnt exist")
        except (OSError, EnvironmentError):
            raise Exception("Internal Error Detected")

    def download_artifact(self, url: str, artifact_type: ArtifactType) -> tuple[tempfile.TemporaryDirectory | None, str, int]: # returns the size of the downloaded huggingface artifact
        size: int = 0

        tempdir: tempfile.TemporaryDirectory = tempfile.TemporaryDirectory()

        repo_id: str = self._get_repo_id_from_url(url, artifact_type)
        storage_name: str = repo_id.replace("/", "_")

        self._huggingface_pull(repo_id, tempdir, artifact_type)

        for ele in os.scandir(tempdir.name):
            size += os.stat(ele).st_size

        archive_dir = shutil.make_archive(storage_name, "gztar", root_dir=tempdir.name, base_dir=tempdir.name)

        return tempdir, archive_dir, size