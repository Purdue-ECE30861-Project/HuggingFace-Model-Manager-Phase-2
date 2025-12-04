from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List
import logging

from pydantic import validate_call

from src.contracts.artifact_contracts import ArtifactQuery, ArtifactMetadata, Artifact, ArtifactID, ArtifactType, \
    ArtifactName, \
    ArtifactRegEx, ArtifactData
from src.backend_server.model.dependencies import DependencyBundle
from .enums import *
from .register_deferred import RaterTaskManager
from .register_direct import \
    register_data_store_model, register_data_store_artifact, update_data_store_model, update_data_store_artifact
from ..data_store.database_connectors.mother_db_connector import DBManager
from src.backend_server.model.downloaders.base_downloader import BaseArtifactDownloader
from .name_extraction import generate_unique_id
from src.backend_server.model.downloaders.gh_downloader import GHArtifactDownloader
from src.backend_server.model.downloaders.hf_downloader import HFArtifactDownloader
from ..data_store.s3_manager import S3BucketManager
from src.backend_server.model.llm_api import LLMAccessor

logger = logging.getLogger(__name__)


class ArtifactAccessor:
    def __init__(self, db: DBManager,
                 s3: S3BucketManager,
                 llm_accessor: LLMAccessor,
                 rater_task_manager: RaterTaskManager,
                 num_processors: int = 1,
                 ingest_score_threshold: float = 0.5,
                 ):
        logger.info("Artifact Accessor is Started")
        self.rater_task_manager = rater_task_manager
        self.dependencies: DependencyBundle = DependencyBundle(
            db=db,
            s3=s3,
            llm_accessor=llm_accessor,
            num_processors=num_processors,
            ingest_score_threshold=ingest_score_threshold
        )

    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        result = self.dependencies.db.router_artifact.db_artifact_get_query(body, offset)

        if not result:
            logger.error(f"FAILED: get_artifacts {body.__dict__}")
            return GetArtifactsEnum.TOO_MANY_ARTIFACTS, []
        return GetArtifactsEnum.SUCCESS, result

    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact | None]:
        result: Artifact = self.dependencies.db.router_artifact.db_artifact_get_id(id.id, artifact_type)
        if not result:
            logger.error(f"FAILED: get_artifact {id.id}")
            return GetArtifactEnum.DOES_NOT_EXIST, result

        result.data.download_url = self.dependencies.s3_manager.s3_generate_presigned_url(id.id)

        return GetArtifactEnum.SUCCESS, result


    @validate_call
    def get_artifact_by_name(self, name: ArtifactName) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        results = self.dependencies.db.router_artifact.db_artifact_get_name(name)

        if not results:
            logger.error(f"FAILED: get_artifact_by_name {name.name}")
            return GetArtifactEnum.DOES_NOT_EXIST, []

        results_reformatted: list[ArtifactMetadata] = [model.generate_metadata() for model in results]
        return GetArtifactEnum.SUCCESS, results_reformatted

    @validate_call
    def get_artifact_by_regex(self, regex_exp: ArtifactRegEx) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        results = self.dependencies.db.router_artifact.db_artifact_get_regex(regex_exp)

        if not results:
            logger.error(f"FAILED: get_artifact_by_regex {regex_exp.regex}")
            return GetArtifactEnum.DOES_NOT_EXIST, []
        results_reformatted: list[ArtifactMetadata] = [model.generate_metadata() for model in results]
        return GetArtifactEnum.SUCCESS, results_reformatted

    @validate_call
    async def register_artifact_deferred(self, artifact_type: ArtifactType, body: ArtifactData) -> RegisterArtifactEnum:
        artifact_id: str = generate_unique_id(body.url)

        if self.dependencies.db.router_artifact.db_artifact_exists(artifact_id, artifact_type):
            logger.error(f"FAILED: url: {body.url} artifact_id {artifact_id} type {artifact_type.name} already exists")
            return RegisterArtifactEnum.ALREADY_EXISTS

        push_result: bool = await self.rater_task_manager.submit(artifact_id, artifact_type, body)
        if not push_result:
            return RegisterArtifactEnum.INTERNAL_ERROR
        return RegisterArtifactEnum.DEFERRED

    @validate_call
    def register_artifact(self, artifact_type: ArtifactType, body: ArtifactData) -> tuple[RegisterArtifactEnum, Artifact | None]:
        artifact_id: str = generate_unique_id(body.url)

        if self.dependencies.db.router_artifact.db_artifact_exists(artifact_id, artifact_type):
            logger.error(f"FAILED: url: {body.url} artifact_id {artifact_id} type {artifact_type.name} already exists")
            return RegisterArtifactEnum.ALREADY_EXISTS, None

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
                return register_data_store_model(artifact_id, body, size, temp_path, self.dependencies)
            return register_data_store_artifact(artifact_id, body, artifact_type, size, temp_path, self.dependencies)

    @validate_call
    async def update_artifact_deferred(self, artifact_type: ArtifactType, artifact_id: ArtifactID, body: Artifact) -> UpdateArtifactEnum:
        if not self.dependencies.db.router_artifact.db_artifact_exists(artifact_id.id, artifact_type):
            logger.error(f"FAILED: url: {body.url} artifact_id {artifact_id} type {artifact_type.name} does not exist")
            return UpdateArtifactEnum.DOES_NOT_EXIST

        push_result: bool = await self.rater_task_manager.submit(artifact_id.id, artifact_type, body)
        if not push_result:
            return UpdateArtifactEnum.DISQUALIFIED
        return UpdateArtifactEnum.DEFERRED

    @validate_call
    def update_artifact(self, artifact_type: ArtifactType, artifact_id: ArtifactID, body: Artifact) -> UpdateArtifactEnum:
        if not self.dependencies.db.router_artifact.db_artifact_exists(artifact_id.id, artifact_type):
            logger.error(f"FAILED: url: {body.url} artifact_id {artifact_id} type {artifact_type.name} does not exist")
            return UpdateArtifactEnum.DOES_NOT_EXIST

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
                artifact, readme, names, rating = self.dependencies.db.db_get_snapshot_model(artifact_id.id)
                update_result = update_data_store_model(body, size, temp_path, self.dependencies)
                if update_result != UpdateArtifactEnum.SUCCESS:
                    self.dependencies.db.db_restore_snapshot_model(artifact, readme, names, rating)

            else:
                update_result = update_data_store_artifact(body, size, temp_path, self.dependencies)

            return update_result


    @validate_call
    def delete_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> GetArtifactEnum:
        if not self.dependencies.db.router_artifact.db_artifact_delete(id.id, artifact_type):
            return GetArtifactEnum.DOES_NOT_EXIST
        self.dependencies.s3_manager.s3_artifact_delete(id.id)

        return GetArtifactEnum.SUCCESS
    # Remove the old _download_and_validate method - it's now handled by ArtifactDownloader
