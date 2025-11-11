from tempfile import TemporaryDirectory

import hashlib

from typing import List
import logging

from enum import Enum
from unicodedata import category

from jedi.api.completion import extract_imported_names
from pydantic import validate_call
from pathlib import Path

from src.contracts.artifact_contracts import ArtifactQuery, ArtifactMetadata, Artifact, ArtifactID, ArtifactType, ArtifactName, \
    ArtifactRegEx, ArtifactData
from src.contracts.model_rating import ModelRating
from data_store.s3_manager import S3BucketManager
from data_store.database import SQLMetadataAccessor
from data_store.downloaders.hf_downloader import HFArtifactDownloader
from .model_rater import ModelRater, ModelRaterEnum


class GetArtifactsEnum(Enum):
    SUCCESS = 200
    TOO_MANY_ARTIFACTS = 413

class GetArtifactEnum(Enum):
    SUCCESS = 200
    DOES_NOT_EXIST = 404

class RegisterArtifactEnum(Enum):
    SUCCESS = 200
    ALREADY_EXISTS = 409
    DISQUALIFIED = 424
    BAD_REQUEST = 400


def extract_name_from_url(url: str) -> str:
    return "GoobyGoober"

def determine_artifact_type(url: str, filepath: Path) -> ArtifactType:
    return ArtifactType.model

class ArtifactAccessor:
    def __init__(self, amdb_url: str,
                 s3_url: str = None,
                 num_processors: int = 1
                 ):
        self.db: SQLMetadataAccessor = SQLMetadataAccessor(db_url=amdb_url)
        self.s3_manager = S3BucketManager(endpoint_url=s3_url)
        self.num_processors: int = num_processors

    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        result = self.db.get_by_query(body, offset)

        if not result:
            return GetArtifactsEnum.TOO_MANY_ARTIFACTS, []
        return GetArtifactsEnum.SUCCESS, result


    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact | None]:
        result = self.db.get_by_id(id, artifact_type)

        if not result:
            return GetArtifactEnum.DOES_NOT_EXIST, result
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
        temporary_rater: ModelRater = ModelRater()
        temporary_downloader: HFArtifactDownloader = HFArtifactDownloader()

        temp_file: TemporaryDirectory
        size: int = 0

        try:
            temp_file, size = temporary_downloader.download_artifact(body.url, artifact_type)
        except FileNotFoundError:
            return RegisterArtifactEnum.BAD_REQUEST, None
        except (OSError, EnvironmentError):
            # add logs here
            return RegisterArtifactEnum.DISQUALIFIED, None

        temp_path: Path = Path(temp_file.name)
        new_artifact: Artifact = Artifact(
            metadata=ArtifactMetadata(
                    name=extract_name_from_url(body.url),
                    id=self._generate_unique_id(body.url),
                    type=determine_artifact_type(body.url, temp_path) # replace later with actual code
                ),
            data=body
        )
        rating: ModelRating = ModelRating.generate_rating(temp_path, new_artifact, self.num_processors)

        #
        # rate_response: ModelRaterEnum
        # rate_content: ModelRating
        #
        # rate_response, rate_content = temporary_rater.rate_model_ingest(tempfile)

        # from here do asynchronous ingestion with model rater

        #results = self.db.add_to_db()

    @validate_call
    def update_artifact(self, artifact_type: ArtifactType, id: ArtifactID, body: Artifact) -> tuple[GetArtifactEnum, None]:
        raise NotImplementedError()

    @validate_call
    def delete_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact]:
        try:
            # Check if artifact exists
            if not self.db.adb_artifact_exists_in_mysql(id.id):
                error_metadata = ArtifactMetadata(
                    id=id.id, name="not-found", version="0.0.0", type=artifact_type
                )
                error_data = ArtifactData(url="")
                error_artifact = Artifact(metadata=error_metadata, data=error_data)
                return GetArtifactEnum.DOES_NOT_EXIST, error_artifact

            # Get metadata before deletion
            name = ArtifactName(name=id.id)
            results = self.db.adb_artifact_get_metadata_by_name(name)
        
            if results:
                metadata = results[0]
                # Delete from S3
                self.s3_manager.s3_artifact_delete(id.id)
                # Note: Database deletion would need a new method in AccessorDatabase
            
                data = ArtifactData(url="")  # Empty URL since deleted
                artifact = Artifact(metadata=metadata, data=data)
                return GetArtifactEnum.SUCCESS, artifact
        
            return GetArtifactEnum.DOES_NOT_EXIST, None
        
        except Exception as e:
            logging.error(f"Error in delete_artifact: {e}")
            return GetArtifactEnum.INVALID_REQUEST, None

    def _generate_unique_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _extract_metadata(self, artifact_content: bytes, artifact_type: ArtifactType, artifact_id: str) -> ArtifactMetadata:
        return ArtifactMetadata(
            id=artifact_id,
            name=f"artifact_{artifact_id}",
            version="1.0.0",
            type=artifact_type
        )

    # Remove the old _download_and_validate method - it's now handled by ArtifactDownloader

async def artifact_accessor() -> ArtifactAccessor:
    return ArtifactAccessor(s3_url="http://127.0.0.1:9000")
