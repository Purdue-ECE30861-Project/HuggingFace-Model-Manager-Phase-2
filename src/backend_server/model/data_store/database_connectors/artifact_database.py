from __future__ import annotations

import json
import re
from typing import Optional
from typing import override, Dict, Any

from pydantic import HttpUrl
from pydantic_core import ValidationError
from sqlalchemy import Dialect, func
from sqlalchemy import Engine, JSON
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql import expression
from sqlalchemy.types import TypeDecorator, String, Text
from sqlmodel import Field, SQLModel, Session, create_engine, select  # pyright: ignore[reportUnknownVariableType]
from typing_extensions import Literal

from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactQuery, ArtifactType, ArtifactData
from src.contracts.model_rating import ModelRating
from src.backend_server.model.data_store.db_utils import *
from .serializers import HttpUrlSerializer
from .database_schemas import DBModelSchema, DBCodeSchema, DBDSetSchema, DBArtifactSchema, ModelLinkedArtifactNames
from .base_database import DBAccessorBase
import logging


logger = logging.getLogger(__name__)


class DBAccessorArtifact(DBAccessorBase): # I assume we use separate tables for cost, lineage, etc
    def model_insert(self, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
        pass

    def model_delete(self):
        pass

    def model_update(self):
        pass

    def artifact_insert(self):
        pass

    def artifact_delete(self):
        pass

    def artifact_update(self):
        pass

    def artifact_get_name(self):
        pass

    def artifact_get_regex(self):
        pass

    def artifact_get_id(self):
        pass

    def artifact_get_query(self):
        pass

    def artifact_exists(self):
        pass

    def database_reset(self):
        pass

    def add_to_db(self, artifact: ArtifactDataDB) -> bool: # return false if in DB already
        try:
            if self.is_in_db(artifact.rating.name, ArtifactType(artifact.rating.category)):
                return False
            with Session(self.engine) as session:
                session.add(artifact)
                session.commit()
            return True
        except Exception as e:
            logger.error(e)
            return False
    
    def get_by_name(self, name: str) -> list[ArtifactDataDB]:
        with Session(self.engine) as session:
            # Use our database-agnostic JSON extraction
            query = select(ArtifactDataDB).where(
                JsonExtract(ArtifactDataDB.rating, '$.name') == name,
            )
            return list(session.exec(query).all())

    def is_in_db(self, name: str, artifact_type: ArtifactType) -> bool: # must assess by url and other features as well
        with Session(self.engine) as session:
            # Use our database-agnostic JSON extraction
            query = select(ArtifactDataDB).where(
                JsonExtract(ArtifactDataDB.rating, '$.name') == name,
                JsonExtract(ArtifactDataDB.rating, '$.category') == artifact_type
            )
            return len(session.exec(query).all()) > 0

    def is_in_db_id(self, id: str, artifact_type: ArtifactType) -> bool:
        with Session(self.engine) as session:
            # Use our database-agnostic JSON extraction
            query = select(ArtifactDataDB).where(
                ArtifactDataDB.id == id,
                JsonExtract(ArtifactDataDB.rating, '$.category') == artifact_type
            )
            return len(session.exec(query).all()) > 0
    
    def get_all(self) -> list[ArtifactDataDB]|None:
        with Session(self.engine) as session:
            selection = select(ArtifactDataDB)
            artifact = session.exec(selection)
            return list(artifact.fetchall())

    def get_by_regex(self, regex: str) -> list[ArtifactDataDB]|None:
        with Session(self.engine) as session:
            query = select(ArtifactDataDB) \
                .where(JsonExtract(ArtifactDataDB.rating, '$.name').regexp_match(regex))
            result = session.exec(query).fetchall()

            if not result:
                return None
            return result

    def get_by_query(self, query: ArtifactQuery, offset: str) -> list[ArtifactMetadata]|None: # return NONE if there are TOO MANY artifacts. If no matches return empty list. This endpoint does not call for not found errors
        if query.types is None:
            query.types = [ArtifactType.code, ArtifactType.dataset, ArtifactType.model]
        with Session(self.engine) as session:
            if query.name == "*":
                sql_query = select(ArtifactDataDB)
            else:
                sql_query = select(ArtifactDataDB).where(
                    JsonExtract(ArtifactDataDB.rating, '$.name') == query.name,
                    JsonExtract(ArtifactDataDB.rating, '$.category').in_(query.types)
                )
            artifacts = session.exec(sql_query).fetchall()

            return [ArtifactMetadata(name=artifact.rating.name, id=str(artifact.id), type=ArtifactType(artifact.rating.category)) for artifact in artifacts]

    def get_by_id(self, id: str, artifact_type: ArtifactType) -> Artifact|None:
        with Session(self.engine) as session:
            sql_query = select(ArtifactDataDB).where(
                ArtifactDataDB.id == id,
                            JsonExtract(ArtifactDataDB.rating, '$.category') == artifact_type)
            artifact = session.exec(sql_query).first()
            if not artifact:
                return None
            return Artifact(
                metadata=ArtifactMetadata(
                    name=artifact.rating.name,
                    id=str(artifact.id),
                    type=ArtifactType(artifact.rating.category)
                ),
                data=ArtifactData(
                    url=str(artifact.url),
                    download_url="")
            )
                
    def update_artifact(self, id: str, updated: Artifact, artifact_type: ArtifactType) -> bool: # should return false if the artifact is not found
        with Session(self.engine) as session:
            sanity_query = select(ArtifactDataDB).where(
                ArtifactDataDB.id == id,
                            JsonExtract(ArtifactDataDB.rating, "$.category") == artifact_type)
            artifact = session.exec(sanity_query).first()
            if not artifact:
                return False
            artifact.update_from_artifact(updated)
            session.add(artifact)
            session.commit()
            session.refresh(artifact)

        return True

    def delete_artifact(self, id: str, artifact_type: ArtifactType) -> bool: # return false if artifact is not found
        with Session(self.engine) as session:
            statement = select(ArtifactDataDB).where(
                ArtifactDataDB.id == id,
                            JsonExtract(ArtifactDataDB.rating, "$.category") == artifact_type)
            artifact = session.exec(statement).first()
            if not artifact:
                return False
            session.delete(artifact)
            session.commit()

        return True