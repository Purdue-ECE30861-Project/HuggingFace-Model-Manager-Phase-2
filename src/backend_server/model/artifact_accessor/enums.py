from enum import Enum


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