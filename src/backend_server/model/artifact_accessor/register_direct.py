import shutil
from pathlib import Path
import botocore.exceptions as botoexc
import hashlib

from .enums import *
from src.backend_server.model.data_store.database_connectors.artifact_database import SQLMetadataAccessor, ArtifactDataDB
from src.backend_server.model.data_store.s3_manager import S3BucketManager
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactData, ArtifactType
from src.contracts.model_rating import ModelRating


def extract_name_from_url(url: str) -> str:
    return "GoobyGoober" # implement me later

def generate_unique_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def register_data_store(
        s3_manager: S3BucketManager,
        db: SQLMetadataAccessor,
        new_artifact: Artifact,
        rating: ModelRating,
        tempdir: Path
) -> tuple[RegisterArtifactEnum, Artifact | None]:
    archive_path = shutil.make_archive(str(tempdir.resolve()), "xztar", root_dir=tempdir)
    try:
        s3_manager.s3_artifact_upload(new_artifact.metadata.id, Path(archive_path))
        if not db.add_to_db(ArtifactDataDB.create_from_artifact(new_artifact, rating)):
            raise IOError("Database Failure")
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
            name=extract_name_from_url(data.url),
            id=generate_unique_id(data.url),
            type=artifact_type  # replace later with actual code
        ),
        data=data
    )
    rating: ModelRating = ModelRating.generate_rating(tempdir, new_artifact, num_processors)

    return new_artifact, rating