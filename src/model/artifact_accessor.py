from enum import Enum
from pydantic import validate_call
from ..controller.api_types import *


class GetArtifactsEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    TOO_MANY_ARTIFACTS = 413

class GetArtifactEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    DOES_NOT_EXIST = 404

class RegisterArtifactEnum(Enum):
    SUCCESS = 200
    INVALID_REQUEST = 400
    ALREADY_EXISTS = 409
    DISQUALIFIED = 424

class ArtifactAccessor:
    @validate_call
    def get_artifacts(self, body: ArtifactQuery, offset: str) -> tuple[GetArtifactsEnum, List[ArtifactMetadata]]:
        raise NotImplementedError()

    @validate_call
    def get_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact]:
        raise NotImplementedError()

    @validate_call
    def update_artifact(self, artifact_type: ArtifactType, id: ArtifactID, body: Artifact) -> tuple[GetArtifactEnum, None]:
        raise NotImplementedError()

    @validate_call
    def delete_artifact(self, artifact_type: ArtifactType, id: ArtifactID) -> tuple[GetArtifactEnum, Artifact]:
        raise NotImplementedError()

    @validate_call
    def register_artifact(self, artifact_type: ArtifactType, body: ArtifactData) -> tuple[RegisterArtifactEnum, Artifact]:
        raise NotImplementedError()

    @validate_call
    def get_artifact_by_name(self, name: ArtifactName) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        raise NotImplementedError()

    @validate_call
    def get_artifact_by_regex(self, regex_exp: ArtifactRegEx) -> tuple[GetArtifactEnum, list[ArtifactMetadata]]:
        raise NotImplementedError()


async def artifact_accessor() -> ArtifactAccessor:
    return ArtifactAccessor()