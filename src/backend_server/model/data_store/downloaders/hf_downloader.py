import os
from pathlib import Path
from typing import override

import huggingface_hub.utils
from huggingface_hub import snapshot_download

from src.backend_server.model.data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from src.backend_server.model.data_store.downloaders.base_downloader import BaseArtifactDownloader
from src.contracts.artifact_contracts import ArtifactType


class HFArtifactDownloader(BaseArtifactDownloader):
    def _validate_url(self, url: str) -> bool:
        """Internal method to validate URL format"""
        return url.startswith(('http://huggingface.co', 'https://huggingface.co'))

    def _get_repo_id_from_url(self, url: str, artifact_type: ArtifactType) -> str:
        split: list[str] = url.split("/")

        match artifact_type:
            case ArtifactType.model:
                if len(split) < 5:
                    raise NameError("Invalid HF Url")
                return f"{split[3]}/{split[4]}"
            case ArtifactType.dataset:
                if len(split) < 6:
                    raise NameError("Invalid HF Url")
                if split[3] != "datasets":
                    raise NameError("Specified type of dataset, hugginface url format requires 'dataset' path")
                return f"{split[4]}/{split[5]}"
            case ArtifactType.code:
                raise TypeError("Cannot retrieve code from huggingface URL, specify github url")

    def _huggingface_pull(self, repo_id: str, tempdir: Path, artifact_type: ArtifactType):
        try:
            print(repo_id)
            snapshot_download(repo_id=repo_id, local_dir=tempdir, repo_type="dataset") \
                if artifact_type == "dataset" else \
                snapshot_download(repo_id=repo_id, local_dir=tempdir)
        except (huggingface_hub.utils.RepositoryNotFoundError, huggingface_hub.utils.RevisionNotFoundError):
            raise FileNotFoundError("Requested repository doesnt exist")

    @override
    def download_artifact(self, url: str, artifact_type: ArtifactType, tempdir: Path) -> float: # returns the size of the downloaded huggingface artifact
        size: int = 0

        repo_id: str = self._get_repo_id_from_url(url, artifact_type)

        self._huggingface_pull(repo_id, tempdir, artifact_type)

        for ele in os.scandir(tempdir):
            size += os.stat(ele).st_size

        return size / 10e6


def model_get_related_artifacts(tempdir: Path) -> ModelLinkedArtifactNames:
    # MICHAEL RAY (MALINKYZUBR) AKA DUMBSHIT FORGOT TO IMPLEMENT> IMPLEMENT ASAP OR DIE! -Michael Ray
    raise NotImplementedError()