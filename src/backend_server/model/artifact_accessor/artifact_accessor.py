import shutil
from tempfile import TemporaryDirectory

import hashlib

from typing import List
import logging

from enum import Enum
from unicodedata import category

from jedi.api.completion import extract_imported_names
from pydantic import validate_call, HttpUrl
from pathlib import Path
import botocore.exceptions as botoexc

from src.contracts.artifact_contracts import ArtifactQuery, ArtifactMetadata, Artifact, ArtifactID, ArtifactType, ArtifactName, \
    ArtifactRegEx, ArtifactData
from .register_direct import generate_unique_id, register_data_store, artifact_and_rating_direct
from .enums import *
from src.contracts.model_rating import ModelRating
from ..data_store.s3_manager import S3BucketManager
from ..data_store.database import SQLMetadataAccessor
from ..data_store.downloaders.hf_downloader import HFArtifactDownloader
from src.backend_server.model.data_store.database import ArtifactDataDB
from src.backend_server.model.model_rater import ModelRater, ModelRaterEnum


class ArtifactAccessor:
    def __init__(self, db: SQLMetadataAccessor,
                 s3: S3BucketManager,
                 num_processors: int = 1,
                 ingest_score_threshold: float = 0.5
                 ):
        self.db: SQLMetadataAccessor = db
        self.s3_manager = s3
        self.num_processors: int = num_processors
        self.ingest_score_threshold: float = ingest_score_threshold

    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        result = self.db.get_by_query(body, offset)

        if not result:
            return GetArtifactsEnum.TOO_MANY_ARTIFACTS, []
        return GetArtifactsEnum.SUCCESS, result


    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact | None]:
        result: Artifact = self.db.get_by_id(id.id, artifact_type)
        if not result:
            return GetArtifactEnum.DOES_NOT_EXIST, result

        result.data.download_url = self.s3_manager.s3_generate_presigned_url(id.id)

        return GetArtifactEnum.SUCCESS, result


    @validate_call
    def get_artifact_by_name(self, name: ArtifactName) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        results = self.db.get_by_name(name.name)

        if not results:
            return GetArtifactEnum.DOES_NOT_EXIST, []

        results_reformatted: list[ArtifactMetadata] = [model.generate_metadata() for model in results]
        return GetArtifactEnum.SUCCESS, results_reformatted

    @validate_call
    def get_artifact_by_regex(self, regex_exp: ArtifactRegEx) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        results = self.db.get_by_regex(regex_exp.regex)

        if not results:
            return GetArtifactEnum.DOES_NOT_EXIST, []
        results_reformatted: list[ArtifactMetadata] = [model.generate_metadata() for model in results]
        return GetArtifactEnum.SUCCESS, results_reformatted

    @validate_call
    def register_artifact_deferred(self, artifact_type: ArtifactType, body: ArtifactType):
        pass

    @validate_call
    def register_artifact(self, artifact_type: ArtifactType, body: ArtifactData) -> tuple[RegisterArtifactEnum, Artifact | None]:
        # NEEDS LOGS
        temporary_downloader: HFArtifactDownloader = HFArtifactDownloader()
        artifact_id: str = generate_unique_id(body.url)

        if self.db.is_in_db_id(artifact_id, artifact_type):
            return RegisterArtifactEnum.ALREADY_EXISTS, None

        with TemporaryDirectory() as tempdir:
            size: int = 0

            try:
                size = temporary_downloader.download_artifact(body.url, artifact_type, Path(tempdir))
            except FileNotFoundError:
                return RegisterArtifactEnum.BAD_REQUEST, None
            except (OSError, EnvironmentError):
                return RegisterArtifactEnum.DISQUALIFIED, None

            temp_path: Path = Path(tempdir)
            new_artifact, rating = artifact_and_rating_direct(temp_path, body, artifact_type, self.num_processors)

            if rating.net_score < self.ingest_score_threshold:
                return RegisterArtifactEnum.DISQUALIFIED, None

            return register_data_store(self.s3_manager, self.db, new_artifact, rating, temp_path)


    @validate_call
    def update_artifact(self, artifact_type: ArtifactType, id: ArtifactID, body: Artifact) -> GetArtifactEnum:
        if not self.db.update_artifact(id.id, body, artifact_type):
            return GetArtifactEnum.DOES_NOT_EXIST

        temporary_downloader: HFArtifactDownloader = HFArtifactDownloader()
        with TemporaryDirectory() as tempdir:
            try:
                size = temporary_downloader.download_artifact(body.data.url, artifact_type, Path(tempdir))
            except (FileNotFoundError, OSError, EnvironmentError):
                return GetArtifactEnum.DOES_NOT_EXIST

            archive_path = shutil.make_archive(tempdir, "xztar", root_dir=tempdir)
            self.s3_manager.s3_artifact_upload(id.id, Path(archive_path))

            return GetArtifactEnum.SUCCESS


    @validate_call
    def delete_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> GetArtifactEnum:
        if not self.db.delete_artifact(id.id, artifact_type):
            return GetArtifactEnum.DOES_NOT_EXIST
        self.s3_manager.s3_artifact_delete(id.id)

        return GetArtifactEnum.SUCCESS
    # Remove the old _download_and_validate method - it's now handled by ArtifactDownloader

async def artifact_accessor() -> ArtifactAccessor:
    return ArtifactAccessor(s3_url="http://127.0.0.1:9000")
