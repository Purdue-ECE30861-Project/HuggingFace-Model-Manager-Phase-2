import hashlib
import shutil
from pathlib import Path

import botocore.exceptions as botoexc

from src.backend_server.model.data_store.s3_manager import S3BucketManager
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
from src.contracts.model_rating import ModelRating
from .enums import *
from ..data_store.database_connectors.database_schemas import ModelLinkedArtifactNames
from ..data_store.database_connectors.mother_db_connector import DBManager
from ..data_store.downloaders.base_downloader import extract_name_from_url, generate_unique_id
from ..data_store.downloaders.hf_downloader import model_get_related_artifacts


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
    if new_artifact.type == ArtifactType.model:
        associated_artifacts: ModelLinkedArtifactNames = model_get_related_artifacts(tempdir)
        return db.router_artifact.db_model_ingest(
            new_artifact,
            associated_artifacts,
            size,
            collect_readmes(tempdir),
        )
    return db.router_artifact.db_artifact_ingest(
        new_artifact,
        size,
        collect_readmes(tempdir)
    )

def register_data_store(
        s3_manager: S3BucketManager,
        db: DBManager,
        new_artifact: Artifact,
        size: float,
        rating: ModelRating,
        tempdir: Path
) -> tuple[RegisterArtifactEnum, Artifact | None]:
    archive_path = shutil.make_archive(str(tempdir.resolve()), "xztar", root_dir=tempdir)
    try:
        s3_manager.s3_artifact_upload(new_artifact.metadata.id, Path(archive_path))
        if not register_database(db, new_artifact, tempdir, size):
            raise IOError("Database Failure")
        if not db.router_rating.db_rating_add(new_artifact.metadata.id, rating):
            raise IOError("Failed to ingest rating due to database problem")
    except botoexc.ClientError as e:
        return RegisterArtifactEnum.DISQUALIFIED, None
    except IOError as e:
        return RegisterArtifactEnum.DISQUALIFIED, None

    return RegisterArtifactEnum.SUCCESS, new_artifact


def artifact_and_rating_direct(
        tempdir: Path,
        data: ArtifactData,
        artifact_type: ArtifactType,
        num_processors: int
) -> tuple[Artifact, ModelRating]:
    new_artifact: Artifact = Artifact(
        metadata=ArtifactMetadata(
            name=extract_name_from_url(data.url, artifact_type),
            id=generate_unique_id(data.url),
            type=artifact_type
        ),
        data=data
    )
    rating: ModelRating = ModelRating.generate_rating(tempdir, new_artifact, num_processors)

    return new_artifact, rating