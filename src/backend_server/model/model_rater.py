from enum import IntEnum

from pydantic import validate_call

from src.backend_server.model.data_store.artifact_database import SQLMetadataAccessor
from src.contracts.artifact_contracts import ArtifactID, ArtifactType
from src.contracts.model_rating import ModelRating


class ModelRaterEnum(IntEnum):
    SUCCESS = 200
    NOT_FOUND = 404
    INTERNAL_ERROR = 500
class ModelRater:
    def __init__(self, database_accessor: SQLMetadataAccessor):
        self.accessor = database_accessor

    @validate_call
    async def rate_model(self, id: ArtifactID) -> tuple[ModelRaterEnum, ModelRating | None]:
        result = self.accessor.get_by_id(id.id, ArtifactType.model)

        if not result:
            return ModelRaterEnum.NOT_FOUND, None
        return ModelRaterEnum.SUCCESS, result