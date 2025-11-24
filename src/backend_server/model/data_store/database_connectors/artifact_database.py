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
from .database_schemas import DBModelSchema, DBCodeSchema, DBDSetSchema, DBArtifactSchema, ModelLinkedArtifactNames, \
    DBConnectiveSchema, DBConnectiveRelation, DBArtifactReadmeSchema
import logging


logger = logging.getLogger(__name__)


def get_table_from_type(artifact_type: ArtifactType):
    match artifact_type:
        case ArtifactType.model:
            return DBModelSchema
        case ArtifactType.dataset:
            return DBDSetSchema
        case ArtifactType.code:
            return DBCodeSchema
    raise Exception("Somehow didnt match any table...")


class DBReadmeAccessor:
    @staticmethod
    def artifact_insert_readme(engine: Engine, artifact_id: str, artifact_type: ArtifactType, readme_content: str):
        with Session(engine) as session:
            readme_sch_content: DBArtifactReadmeSchema = DBArtifactReadmeSchema(
                id=artifact_id,
                artifact_type=artifact_type,
                readme_content=readme_content,
            )
            session.add(readme_sch_content)
            session.commit()

    @staticmethod
    def artifact_delete_readme(engine: Engine, artifact_id: str, artifact_type: ArtifactType):
        with Session(engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.artifact_id == artifact_id,
                DBArtifactReadmeSchema.artifact_type == artifact_type
            )
            result = session.exec(query).first()

class DBConnectionAccessor:
    @staticmethod
    def model_insert_dset_connections(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
        with Session(engine) as session:
            for dset_name in linked_names.linked_dset_names:
                associated_dset_query = select(DBDSetSchema).where(
                    DBDSetSchema.name == dset_name
                )
                associated_dset: DBDSetSchema = session.exec(associated_dset_query).first()
                connection: DBConnectiveSchema = DBConnectiveSchema(
                    src_name=dset_name,
                    src_id=None,
                    dst_name=model.name,
                    dst_id=model.id,
                    relationship=DBConnectiveRelation.MODEL_DATASET
                )
                if associated_dset is not None:
                    connection.src_id = associated_dset.id
                session.add(
                    connection
                )

            session.commit()

    @staticmethod
    def model_insert_code_connections(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
        with Session(engine) as session:
            for code_name in linked_names.linked_code_names:
                associated_code_query = select(DBCodeSchema).where(
                    DBCodeSchema.name == code_name
                )
                associated_code: DBCodeSchema = session.exec(associated_code_query).first()
                connection: DBConnectiveSchema = DBConnectiveSchema(
                    src_name=code_name,
                    src_id=None,
                    dst_name=model.name,
                    dst_id=model.id,
                    relationship=DBConnectiveRelation.MODEL_DATASET
                )
                if associated_code is not None:
                    connection.src_id = associated_code.id
                session.add(
                    connection
                )

            session.commit()

    @staticmethod
    def model_add_parent_model_connection(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
        with Session(engine) as session:
            parent_model_query = select(DBModelSchema).where(
                DBModelSchema.name == linked_names.linked_parent_model_name
            )
            parent_model = session.exec(parent_model_query).first()
            connection: DBConnectiveSchema = DBConnectiveSchema(
                src_name=linked_names.linked_parent_model_name,
                src_id=None,
                dst_name=model.name,
                dst_id=model.id,
                relationship=DBConnectiveRelation.MODEL_DATASET
            )
            if parent_model is not None:
                connection.src_id = parent_model.id
            session.add(connection)
            session.commit()

    @staticmethod
    def model_ingest_connection_insertion(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
        DBConnectionAccessor.model_insert_dset_connections(engine, model, linked_names)
        DBConnectionAccessor.model_insert_code_connections(engine, model, linked_names)
        DBConnectionAccessor.model_add_parent_model_connection(engine, model, linked_names)
        DBConnectionAccessor.ingest_connection_children_insertion(engine, model)

    @staticmethod
    def delete_relation_by_dest_id(engine: Engine, artifact_id: str):
        with Session(engine) as session:
            delete_query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_name == artifact_id
            )
            query_results = session.exec(delete_query).fetchall()
            for result in query_results:
                session.delete(result)
            session.commit()

    @staticmethod
    def ingest_connection_children_insertion(engine: Engine, artifact: DBCodeSchema | DBDSetSchema | DBModelSchema):
        relation_type = DBConnectiveRelation.MODEL_DATASET
        if type(artifact) == DBCodeSchema:
            relation_type = DBConnectiveRelation.MODEL_CODEBASE
        elif type(artifact) == DBModelSchema:
            relation_type = DBConnectiveRelation.MODEL_PARENT_MODEL

        with Session(engine) as session:
            search_query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.src_name == artifact.name,
                DBConnectiveSchema.relationship == relation_type
            )
            search_results = session.exec(search_query).fetchall()
            for result in search_results:
                result.src_id = artifact.id
                session.add(result)
            session.commit()

    @staticmethod
    def connections_delete_by_id(engine: Engine, artifact_id: str):
        with Session(engine) as session:
            dst_id_query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_id == artifact_id
            )
            dst_id_results = session.exec(dst_id_query).fetchall()
            for result in dst_id_results:
                session.delete(result)

            src_id_query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.src_id == artifact_id
            )
            src_id_results = session.exec(src_id_query).fetchall()
            for result in src_id_results:
                result.src_id = None
            session.commit()

    @staticmethod
    def model_get_associated_dset_and_code(engine: Engine, model: DBModelSchema) -> list[DBConnectiveSchema]: # first list is codebases, second is datasets
        with Session(engine) as session:
            query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_name == model.name,
                DBConnectiveSchema.dst_id == model.id,
                DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_DATASET or
                    DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_CODEBASE
            )
            return session.exec(query).fetchall()

    @staticmethod
    def model_get_parent_model(engine: Engine, model: DBModelSchema) -> DBConnectiveSchema:
        with Session(engine) as session:
            query = select(DBConnectiveSchema).where(
                DBConnectiveSchema.dst_name == model.name,
                DBConnectiveSchema.dst_id == model.id,
                DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_PARENT_MODEL
            )
            return session.exec(query).first()


class DBAccessorArtifact: # I assume we use separate tables for cost, lineage, etc
    @staticmethod
    def artifact_insert(engine: Engine, artifact: DBModelSchema, artifact_type: ArtifactType):
        try:
            if DBAccessorArtifact.artifact_exists(engine, artifact.id, artifact_type):
                return False
            with Session(engine) as session:
                session.add(artifact)
                session.commit()
            return True
        except Exception as e:
            logger.error(e)
            return False

    @staticmethod
    def artifact_delete(engine: Engine, artifact_id: str, artifact_type: ArtifactType) -> bool:
        table = get_table_from_type(artifact_type)
        with Session(engine) as session:
            query = select(table).where(
                table.id == artifact_id
            )
            artifact = session.exec(query).first()
            if not artifact:
                return False
            session.delete(artifact)
            session.commit()

        return True

    @staticmethod
    def artifact_update(engine: Engine):
        pass

    @staticmethod
    def artifact_get_by_name(engine: Engine):
        with Session(engine) as session:
            # Use our database-agnostic JSON extraction
            query = select(DBModelSchema, DBDSetSchema, DBCodeSchema).join(
                DBDSetSchema, DBDSetSchema.id == DBModelSchema.id
            ).join(
                DBCodeSchema, DBCodeSchema.id == TableA.id
            ).where(TableA.id == some_id)
            return list(session.exec(query).all())

    @staticmethod
    def artifact_get_by_regex(engine: Engine):
        pass

    @staticmethod
    def artifact_get_by_id(engine: Engine):
        pass

    @staticmethod
    def artifact_get_by_query(engine: Engine):
        pass

    @staticmethod
    def artifact_exists(engine: Engine, artifact_id: str, artifact_type: ArtifactType):
        table = get_table_from_type(artifact_type)
        with Session(engine) as session:
            query = select(table).where(
                table.id == artifact_id
            )
            return session.exec(query).first() is not None

    @staticmethod
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

    @staticmethod
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
    
    def get_all(engine: Engine) -> list[ArtifactDataDB]|None:
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