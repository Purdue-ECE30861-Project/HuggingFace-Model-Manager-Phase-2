from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum

from pydantic.v1 import BaseModel
from sqlalchemy import Text
from sqlmodel import Field, SQLModel  # pyright: ignore[reportUnknownVariableType]

from src.contracts.artifact_contracts import ArtifactMetadata, ArtifactType, Artifact, ArtifactData, ArtifactLineageEdge
from src.contracts.auth_contracts import AuditAction, ArtifactAuditEntry
from .serializers import *


class ArtifactAuditSchemaDB(SQLModel, table=True):
    hash_id: str = Field(primary_key=True)
    id: str = Field(default="Python have me goonin")
    artifact_type: ArtifactType
    name: str
    user: User = Field(sa_type=UserSerializer)
    date: datetime
    action: AuditAction

    @staticmethod
    def generate_from_information(metadata: ArtifactMetadata, user: User, action: AuditAction, time: datetime) -> "ArtifactAuditSchemaDB":
        db_formatted = ArtifactAuditSchemaDB (
            hash_id="",
            id=metadata.id,
            artifact_type=metadata.type,
            name=metadata.name,
            user=user,
            action=action,
            date=time
        )
        hash_id: str = hashlib.sha256(
            db_formatted.model_dump_json()
            .encode("utf-8")
        ).hexdigest()
        db_formatted.hash_id = hash_id

        return db_formatted

    def to_audit_entry(self) -> ArtifactAuditEntry:
        return ArtifactAuditEntry(
            user=self.user,
            date=self.date,
            artifact=ArtifactMetadata(
                id=self.id,
                name=self.name,
                type=self.artifact_type
            ),
            action=self.action
        )


class DBConnectiveRelation(Enum):
    MODEL_DATASET=0
    MODEL_CODEBASE=1
    MODEL_PARENT_MODEL=2

    def to_source_type(self) -> ArtifactType:
        match self:
            case DBConnectiveRelation.MODEL_DATASET:
                return ArtifactType.dataset
            case DBConnectiveRelation.MODEL_CODEBASE:
                return ArtifactType.code
            case DBConnectiveRelation.MODEL_PARENT_MODEL:
                return ArtifactType.model
        return ArtifactType.model

class DBConnectiveSchema(SQLModel, table=True):
    relation_id: int | None = Field(default=None, primary_key=True)
    src_name: str
    src_id: str | None
    dst_name: str
    dst_id: str | None
    relationship: DBConnectiveRelation
    relationship_desc: str = ""
    source_desc: str = ""

    def to_lineage_edge(self) -> ArtifactLineageEdge:
        return ArtifactLineageEdge(
            from_node_artifact_id=self.src_id,
            to_node_artifact_id=self.dst_id,
            relationship=self.relationship_desc
        )

class DBArtifactSchema(SQLModel):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    url: HttpUrl = Field(sa_type=HttpUrlSerializer)
    name: str
    size_mb: float
    type: ArtifactType

    def to_concrete(self) -> DBDSetSchema | DBModelSchema | DBArtifactSchema:
        match self.type:
            case ArtifactType.model:
                return DBModelSchema(**self.__dict__)
            case ArtifactType.code:
                return DBCodeSchema(**self.__dict__)
            case ArtifactType.dataset:
                return DBDSetSchema(**self.__dict__)

        return DBModelSchema(**self.__dict__)

    def to_artifact_metadata(self) -> ArtifactMetadata:
        return ArtifactMetadata(
            id=self.id,
            type=self.type,
            name=self.name
        )

    def to_artifact(self) -> Artifact:
        return Artifact(
            metadata=self.to_artifact_metadata(),
            data=ArtifactData(
                url=str(self.url),
                download_url=""
            )
        )

    @staticmethod
    def from_artifact(artifact: Artifact, size_mb: float) -> "DBArtifactSchema":
        return DBArtifactSchema(
            id=artifact.metadata.id,
            type=artifact.metadata.type,
            name=artifact.metadata.name,
            size_mb=size_mb,
            url=artifact.data.url
        )

class DBDSetSchema(DBArtifactSchema, table=True):
    type: ArtifactType = ArtifactType.dataset

class DBCodeSchema(DBArtifactSchema, table=True):
    type: ArtifactType = ArtifactType.code

class ModelLinkedArtifactNames(BaseModel):
    linked_dset_names: list[str]
    linked_code_names: list[str]
    linked_parent_model_name: str | None
    linked_parent_model_relation: str | None
    linked_parent_model_rel_source: str | None = None

class DBModelSchema(DBArtifactSchema, table=True):
    type: ArtifactType = ArtifactType.model

class DBModelRatingSchema(SQLModel, table=True):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    rating: ModelRating = Field(sa_type=ModelRatingSerializer)

    def to_model_rating(self) -> ModelRating:
        return self.rating


class DBArtifactReadmeSchema(SQLModel, table=True):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    artifact_type: ArtifactType
    name: str
    readme_content: str = Field(sa_type=Text)

    def to_artifact_metadata(self) -> ArtifactMetadata:
        return ArtifactMetadata(
            id=self.id,
            name=self.name,
            type=self.artifact_type
        )

    @staticmethod
    def from_artifact(artifact: Artifact, readme: str) -> "DBArtifactReadmeSchema":
        return DBArtifactReadmeSchema(
            id=artifact.metadata.id,
            artifact_type=artifact.metadata.type,
            name=artifact.metadata.name,
            readme_content=readme
        )

"""
ingest algorithms:
ingest model:
    if code name, check for name in the code table, and assign id
    if dataset name, check for name in dataset table, and assign id
    
ingest dataset or code:
    if any model has the name in their table, assign this id to that model
"""