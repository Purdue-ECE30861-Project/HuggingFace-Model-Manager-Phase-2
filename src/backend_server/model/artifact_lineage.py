from pydantic import validate_call
from enum import IntEnum
from src.contracts.artifact_contracts import ArtifactID, ArtifactLineageGraph


class LineageEnum(IntEnum):
    SUCCESS = 200
    DOES_NOT_EXIST = 404
class LineageGraphAnalyzer:
    @validate_call
    async def get_lineage_graph(self, id: ArtifactID) -> tuple[LineageEnum, ArtifactLineageGraph]:
        raise NotImplementedError()