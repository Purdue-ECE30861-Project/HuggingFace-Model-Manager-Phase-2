from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import override, Dict, Any

from pydantic import HttpUrl
from pydantic.v1 import BaseModel
from pydantic_core import ValidationError
from sqlalchemy import Dialect, JSON
from sqlalchemy.types import TypeDecorator, String
from sqlmodel import Field, SQLModel  # pyright: ignore[reportUnknownVariableType]

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


class DBArtifactSchema(SQLModel):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    url: HttpUrl = Field(sa_type=HttpUrlSerializer)
    name: str
    size_mb: float

class DBDSetSchema(DBArtifactSchema, table=True):
    pass

class DBCodeSchema(DBArtifactSchema, table=True):
    pass

class ModelLinkedArtifactNames(BaseModel):
    linked_dset_name: str | None
    linked_code_name: str | None

class DBModelSchema(DBArtifactSchema, table=True):
    linked_dset_id: str | None
    linked_dset_name: str | None
    linked_code_id: str | None
    linked_code_name: str | None

    @staticmethod
    def from_model_linked_names(names: ModelLinkedArtifactNames, artifact_schema: DBArtifactSchema) -> "DBModelSchema":
        return DBModelSchema(
            **artifact_schema.__dict__,
            **names.__dict__
        )


class DBModelRatingSchema(SQLModel, table=True):
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    name: str
    rating: ModelRating = Field(sa_type=ModelRatingSerializer)


"""
ingest algorithms:
ingest model:
    if code name, check for name in the code table, and assign id
    if dataset name, check for name in dataset table, and assign id
    
ingest dataset or code:
    if any model has the name in their table, assign this id to that model
"""