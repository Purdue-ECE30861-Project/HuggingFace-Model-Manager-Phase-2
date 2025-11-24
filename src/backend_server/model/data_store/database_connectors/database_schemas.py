from __future__ import annotations

import hashlib
from enum import Enum
import json
from datetime import datetime
from typing import override, Dict, Any

from pydantic import HttpUrl
from pydantic.v1 import BaseModel
from pydantic_core import ValidationError
from sqlalchemy import Dialect, JSON, Engine, select, Text
from sqlalchemy.types import TypeDecorator, String
from sqlmodel import Field, SQLModel, Session  # pyright: ignore[reportUnknownVariableType]

from src.contracts.artifact_contracts import ArtifactMetadata, ArtifactType
from src.contracts.auth_contracts import User, AuditAction, ArtifactAuditEntry
from src.contracts.model_rating import ModelRating
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
class DBConnectiveSchema(SQLModel, table=True):
    relation_id: int | None = Field(default=None, primary_key=True)
    src_name: str
    src_id: str | None
    dst_name: str
    dst_id: str | None
    relationship: DBConnectiveRelation
    relationship_desc: str = ""

class DBArtifactSchema(SQLModel):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    url: HttpUrl = Field(sa_type=HttpUrlSerializer)
    name: str
    size_mb: float
    type: ArtifactType

class DBDSetSchema(DBArtifactSchema, table=True):
    type: ArtifactType = ArtifactType.dataset

class DBCodeSchema(DBArtifactSchema, table=True):
    type: ArtifactType = ArtifactType.code

class ModelLinkedArtifactNames(BaseModel):
    linked_dset_names: list[str]
    linked_code_names: list[str]
    linked_parent_model_name: str | None
    linked_parent_model_relation: str | None

class DBModelSchema(DBArtifactSchema, table=True):
    type: ArtifactType = ArtifactType.model


class DBModelRatingSchema(SQLModel, table=True):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    name: str
    rating: ModelRating = Field(sa_type=ModelRatingSerializer)


class DBArtifactReadmeSchema(SQLModel, table=True):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    artifact_type: ArtifactType
    readme_content: str = Field(sa_type=Text)

"""
ingest algorithms:
ingest model:
    if code name, check for name in the code table, and assign id
    if dataset name, check for name in dataset table, and assign id
    
ingest dataset or code:
    if any model has the name in their table, assign this id to that model
"""