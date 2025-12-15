import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import botocore.exceptions as botoexc

from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
from src.contracts.base_model_rating import BaseModelRating
from src.contracts.model_rating import ModelRating
from src.backend_server.model.dependencies import DependencyBundle
from .connection_extraction import model_get_related_artifacts
from .name_extraction import extract_name_from_url
from .enums import *
from ..data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from ..data_store.database_connectors.mother_db_connector import DBManager


def make_zip(src: Path, out: Path):
    subprocess.run(
        ["zip", "-r", "-1", str(out), "."],
        cwd=src,
        check=True
    )


logger = logging.getLogger(__name__)


def collect_readmes(root: Path) -> str:
    # case-insensitive match for names starting with "readme"
    results = []
    for path in root.rglob("*"):
        if path.is_file() and path.stem.lower() == "readme":
            try:
                results.append(path.read_text(encoding="utf-8"))
            except Exception:
                pass  # ignore unreadable files
    return "\n".join(results)

def register_database(
        db: DBManager,
        new_artifact: Artifact,
        tempdir: Path,
        size: float
) -> bool:
    if new_artifact.metadata.type == ArtifactType.model:
        readme: str = collect_readmes(tempdir)
        associated_artifacts: ModelLinkedArtifactNames = model_get_related_artifacts(new_artifact.metadata.name, tempdir, readme)
        return db.router_artifact.db_model_ingest(
            new_artifact,
            associated_artifacts,
            size,
            readme,
        )
    return db.router_artifact.db_artifact_ingest(
        new_artifact,
        size,
        collect_readmes(tempdir)
    )

def model_rate_direct(
        id: str,
        data: ArtifactData,
        size: float,
        tempdir: Path,
        dependencies: DependencyBundle
) -> tuple[Artifact, ModelRating]:
    new_artifact: Artifact = Artifact(
        metadata=ArtifactMetadata(
            name=extract_name_from_url(data.url, ArtifactType.model),
            id=id,
            type=ArtifactType.model,
        ),
        data=data
    )
    if not register_database(dependencies.db, new_artifact, tempdir, size):
        raise IOError("Database Failure")

    rating: ModelRating = ModelRating.generate_rating(tempdir, new_artifact, dependencies)

    return new_artifact, rating

def artifact_to_s3(tempdir: Path, dependencies: DependencyBundle, artifact: Artifact) -> Path:
    print("BEGINNING STORAGE")
    archive_path = tempdir / f"artifact{id}.zip"
    make_zip(
        tempdir,
        archive_path
    )
    print("FINISHED TARING")
    dependencies.s3_manager.s3_artifact_upload(artifact.metadata.id, Path(archive_path))
    print("FINISHED UPLOAD")

def register_data_store_model(
        id: str,
        data: ArtifactData,
        size: float,
        tempdir: Path,
        dependencies: DependencyBundle,
        s3_store: bool = True
) -> tuple[RegisterArtifactEnum, Artifact | None]:
    artifact: Artifact
    rating: ModelRating

    try:
        artifact, rating = model_rate_direct(id, data, size, tempdir, dependencies)
        if rating.net_score < dependencies.ingest_score_threshold:
            logger.error(f"FAILED: {data.url} id {artifact.metadata.id} failed to ingest due to low score")
            dependencies.db.router_artifact.db_artifact_delete(artifact.metadata.id, artifact.metadata.type)
            return RegisterArtifactEnum.DISQUALIFIED, None
        dependencies.db.router_rating.db_rating_add(artifact.metadata.id, BaseModelRating.to_base(rating))

        if s3_store:
            artifact_to_s3(tempdir, dependencies, artifact)
    except botoexc.ClientError as e:
        logger.error(f"FAILED: {e.response['Error']['Message']}")
        return RegisterArtifactEnum.INTERNAL_ERROR, None
    except IOError as e:
        logger.error(f"FAILED: {e}")
        return RegisterArtifactEnum.INTERNAL_ERROR, None
    return RegisterArtifactEnum.SUCCESS, artifact

def register_data_store_artifact(
    id: str,
    data: ArtifactData,
    artifact_type: ArtifactType,
    size: float,
    tempdir: Path,
    dependencies: DependencyBundle,
    s3_store: bool = True
) -> tuple[RegisterArtifactEnum, Artifact | None]:
    try:
        artifact: Artifact = Artifact(
            metadata=ArtifactMetadata(
                name=extract_name_from_url(data.url, artifact_type),
                id=id,
                type=artifact_type,
            ),
            data=data
        )
        if not register_database(dependencies.db, artifact, tempdir, size):
            raise IOError("Database Failure")

        logger.warning(f"SILLY SILLY {os.listdir(tempdir)}")

        if s3_store:
            artifact_to_s3(tempdir, dependencies, artifact)
    except botoexc.ClientError as e:
        logger.error(f"FAILED: {e.response['Error']['Message']}")
        return RegisterArtifactEnum.INTERNAL_ERROR, None
    except IOError as e:
        logger.error(f"FAILED: {e}")
        return RegisterArtifactEnum.INTERNAL_ERROR, None
    return RegisterArtifactEnum.SUCCESS, artifact

def update_data_store_model(
    artifact: Artifact,
    size: float,
    tempdir: Path,
    dependencies: DependencyBundle
) -> UpdateArtifactEnum:
    try:
        if not dependencies.db.router_artifact.db_artifact_update(artifact, size, collect_readmes(
                tempdir)):  # update and resocre models that dpeend on artifact
            raise IOError("Database Failure")

        rating: ModelRating = ModelRating.generate_rating(tempdir, artifact, dependencies)
        if rating.net_score < dependencies.ingest_score_threshold:
            return UpdateArtifactEnum.DISQUALIFIED

        dependencies.db.router_rating.db_rating_add(artifact.metadata.id, BaseModelRating.to_base(rating))

        archive_path = shutil.make_archive(str(tempdir.resolve()), "xztar", root_dir=tempdir)
        dependencies.s3_manager.s3_artifact_upload(artifact.metadata.id, Path(archive_path))
        return UpdateArtifactEnum.SUCCESS
    except botoexc.ClientError as e:
        logger.error(f"FAILED: {e.response['Error']['Message']}")
        return UpdateArtifactEnum.DISQUALIFIED
    except IOError as e:
        logger.error(f"FAILED: {e}")
        return UpdateArtifactEnum.DOES_NOT_EXIST

def update_data_store_artifact(
    artifact: Artifact,
    size: float,
    tempdir: Path,
    dependencies: DependencyBundle
) -> UpdateArtifactEnum:
    try:
        if not dependencies.db.router_artifact.db_artifact_update(artifact, size, collect_readmes(tempdir)): # update and resocre models that dpeend on artifact
            raise IOError("Database Failure")
        archive_path = shutil.make_archive(str(tempdir.resolve()), "xztar", root_dir=tempdir)
        dependencies.s3_manager.s3_artifact_upload(artifact.metadata.id, Path(archive_path))
        return UpdateArtifactEnum.SUCCESS
    except botoexc.ClientError as e:
        logger.error(f"FAILED: {e.response['Error']['Message']}")
        return UpdateArtifactEnum.DISQUALIFIED
    except IOError as e:
        logger.error(f"FAILED: {e}")
        return UpdateArtifactEnum.DOES_NOT_EXIST


