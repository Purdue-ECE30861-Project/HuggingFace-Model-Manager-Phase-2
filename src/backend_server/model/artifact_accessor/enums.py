from enum import IntEnum


class GetArtifactsEnum(IntEnum):
    SUCCESS = 200
    TOO_MANY_ARTIFACTS = 413

class GetArtifactEnum(IntEnum):
    SUCCESS = 200
    DOES_NOT_EXIST = 404

class RegisterArtifactEnum(IntEnum):
    SUCCESS = 201
    ALREADY_EXISTS = 409
    DISQUALIFIED = 424
    BAD_REQUEST = 400,
    DEFERRED = 202