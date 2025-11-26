from __future__ import annotations

import logging
from typing import Type

from sqlalchemy import Engine
from sqlalchemy.orm import relationship
from sqlmodel import Session, select  # pyright: ignore[reportUnknownVariableType]

from src.backend_server.model.data_store.db_utils import *
from src.contracts.artifact_contracts import Artifact, ArtifactType, ArtifactQuery, ArtifactMetadata, ArtifactName
from .database_schemas import DBModelSchema, DBCodeSchema, DBDSetSchema, DBArtifactSchema, ModelLinkedArtifactNames, \
    DBConnectiveSchema, DBConnectiveRelation, DBArtifactReadmeSchema

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


def get_tables() -> tuple[type[DBModelSchema], type[DBDSetSchema], type[DBCodeSchema]]:
    return DBModelSchema, DBDSetSchema, DBCodeSchema


class DBReadmeAccessor:
    @staticmethod
    def artifact_insert_readme(engine: Engine, artifact: Artifact, readme_content: str):
        with Session(engine) as session:
            readme_sch_content: DBArtifactReadmeSchema = DBArtifactReadmeSchema.from_artifact(artifact, readme_content)
            session.add(readme_sch_content)
            session.commit()

    @staticmethod
    def artifact_delete_readme(engine: Engine, artifact_id: str, artifact_type: ArtifactType) -> bool:
        with Session(engine) as session:
            query = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.id == artifact_id,
                DBArtifactReadmeSchema.artifact_type == artifact_type
            )
            result = session.exec(query).first()

            if not result:
                return False
            session.delete(result)
            session.commit()
            return True

class DBConnectionAccessor:
    @staticmethod
    def _model_insert_dset_connections(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
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
    def _model_insert_code_connections(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
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
                    relationship=DBConnectiveRelation.MODEL_CODEBASE
                )
                if associated_code is not None:
                    connection.src_id = associated_code.id
                session.add(
                    connection
                )

            session.commit()

    @staticmethod
    def _model_add_parent_model_connection(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
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
                relationship=DBConnectiveRelation.MODEL_PARENT_MODEL,
                relationship_description=linked_names.linked_parent_model_relation,
                source_desc=linked_names.linked_parent_model_rel_source,
            )
            if parent_model is not None:
                connection.src_id = parent_model.id
            session.add(connection)
            session.commit()

    @staticmethod
    def model_insert(engine: Engine, model: DBModelSchema, linked_names: ModelLinkedArtifactNames):
        if linked_names.linked_dset_names: DBConnectionAccessor._model_insert_dset_connections(engine, model, linked_names)
        if linked_names.linked_code_names: DBConnectionAccessor._model_insert_code_connections(engine, model, linked_names)
        if linked_names.linked_parent_model_name: DBConnectionAccessor._model_add_parent_model_connection(engine, model, linked_names)
        DBConnectionAccessor._ingest_connection_children_insertion(engine, model)

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
    def _ingest_connection_children_insertion(engine: Engine, artifact: DBCodeSchema | DBDSetSchema | DBModelSchema):
        """search for all artifact relations that have the seleected artifact name as a source"""
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
    def non_model_insert(engine: Engine, artifact: DBArtifactSchema):
        DBConnectionAccessor._ingest_connection_children_insertion(engine, artifact)

    @staticmethod
    def connections_delete_by_artifact_id(engine: Engine, artifact_id: str):
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
                (DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_DATASET) |
                (DBConnectiveSchema.relationship == DBConnectiveRelation.MODEL_CODEBASE)
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

    @staticmethod
    def connections_get_all(engine: Engine) -> list[DBConnectiveSchema]|None:
        with Session(engine) as session:
            query = select(DBConnectiveSchema)
            results = session.exec(query).fetchall()

            if not results:
                return None
            return results


class DBArtifactAccessor: # I assume we use separate tables for cost, lineage, etc
    @staticmethod
    def artifact_insert(engine: Engine, artifact: DBArtifactSchema):
        try:
            if DBArtifactAccessor.artifact_exists(engine, artifact.id, artifact.type):
                return False
            with Session(engine) as session:
                session.add(artifact.to_concrete())
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
    def artifact_update(engine: Engine, artifact: Artifact, new_size: float) -> bool:
        with Session(engine) as session:
            table = get_table_from_type(artifact.metadata.type)
            query = select(table).where(
                table.id == artifact.metadata.id,
                table.url == artifact.data.url,
                table.name == artifact.metadata.name
            )
            result: DBArtifactSchema = session.exec(query).first()
            if not result:
                return False
            result.size_mb = new_size
            session.add(result)
            session.commit()

            return True

    @staticmethod
    def artifact_get_by_name(engine: Engine, artifact_name: ArtifactName) -> None|list[DBArtifactSchema]:
        with Session(engine) as session:
            # Use our database-agnostic JSON extraction
            results: list[DBArtifactSchema] = []

            for table in get_tables():
                query = select(table) \
                .where(table.name == artifact_name.name)
                result = session.exec(query).all()

                if result:
                    results += result

            if not results:
                return None
            return results

    @staticmethod
    def artifact_get_by_regex(engine: Engine, regex: str) -> tuple[list[DBArtifactSchema], list[DBArtifactReadmeSchema]]:
        with Session(engine) as session:
            results: list[DBArtifactSchema] = []

            for table in get_tables():
                query = select(table).where(
                    table.name.regexp_match(regex)
                )
                result = session.exec(query).all()
                if result:
                    results += result

            query_readme = select(DBArtifactReadmeSchema).where(
                DBArtifactReadmeSchema.readme_content.regexp_match(regex)
            )
            results_readme = session.exec(query_readme).fetchall()

            return results, results_readme

    @staticmethod
    def artifact_get_by_id(engine: Engine, id: str, artifact_type: ArtifactType) -> None|DBArtifactSchema:
        table = get_table_from_type(artifact_type)
        with Session(engine) as session:
            sql_query = select(table).where(
                table.id == id,
                table.type == artifact_type
            )

            artifact: DBArtifactSchema = session.exec(sql_query).first()
            if not artifact:
                return None
            return artifact

    @staticmethod
    def artifact_get_by_query(engine: Engine, query: ArtifactQuery, offset: str) -> list[DBArtifactSchema]|None:
        if query.types is None:
            query.types = [ArtifactType.code, ArtifactType.dataset, ArtifactType.model]
        tables = [get_table_from_type(type) for type in query.types]
        with Session(engine) as session:
            artifact_results: list[DBArtifactSchema] = []
            if query.name == "*":
                for table in tables:
                    sql_query = select(table)
                    artifact_result = session.exec(sql_query).fetchall()
                    if artifact_result:
                        artifact_results += artifact_result
            else:
                for table in tables:
                    sql_query = select(table).where(
                        table.name == query.name
                    )
                    artifact_results += session.exec(sql_query).fetchall()

            return artifact_results

    @staticmethod
    def artifact_exists(engine: Engine, artifact_id: str, artifact_type: ArtifactType) -> bool:
        table = get_table_from_type(artifact_type)
        with Session(engine) as session:
            query = select(table).where(
                table.id == artifact_id
            )
            return session.exec(query).first() is not None

    @staticmethod
    def get_all(engine: Engine) -> None|list[DBArtifactSchema]:
        with Session(engine) as session:
            results: list[DBArtifactSchema] = []
            for table in get_tables():
                query = select(table)
                result: list[DBArtifactSchema] = session.exec(query).fetchall()
                if result:
                    results += result

            if not results:
                return None
            return results

    # def update_artifact(self, id: str, updated: Artifact, artifact_type: ArtifactType) -> bool: # should return false if the artifact is not found
    #     with Session(self.engine) as session:
    #         sanity_query = select(ArtifactDataDB).where(
    #             ArtifactDataDB.id == id,
    #                         JsonExtract(ArtifactDataDB.rating, "$.category") == artifact_type)
    #         artifact = session.exec(sanity_query).first()
    #         if not artifact:
    #             return False
    #         artifact.update_from_artifact(updated)
    #         session.add(artifact)
    #         session.commit()
    #         session.refresh(artifact)
    #
    #     return True