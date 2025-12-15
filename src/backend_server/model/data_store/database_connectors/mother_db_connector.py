import logging

from sqlalchemy import Engine
from sqlmodel import Session, select

from src.contracts.artifact_contracts import ArtifactQuery, ArtifactName, ArtifactRegEx, ArtifactID, \
    ArtifactLineageGraph, ArtifactCost, ArtifactLineageNode
from .database_schemas import *
from .audit_database import DBAuditAccessor
from .artifact_database import DBArtifactAccessor, DBConnectionAccessor, DBReadmeAccessor
from .model_rating_database import DBModelRatingAccessor
from .base_database import db_reset


logger = logging.getLogger(__name__)


"""
TODO: Need a separate column for accessing that determines if an artifact has finished rating yet. Gets to the database should match this column (eg if true, only then return that entry)
"""
class DBRouterBase:
    def __init__(self, engine: Engine):
        self.engine = engine


class DBRouterArtifact(DBRouterBase):
    def db_artifact_snapshot(self, artifact_id: str,
                           artifact_type: ArtifactType) -> tuple[DBArtifactSchema|None, str|None]:
        result: None | DBArtifactSchema = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_id, artifact_type)
        if not result:
            raise IOError("Artifact Not Exist")

        readme: str|None = DBReadmeAccessor.artifact_get_readme(self.engine, artifact_id, artifact_type)
        if not readme:
            readme = ""

        return result, readme

    def db_model_ingest(self, model_artifact: Artifact,
                        attached_names: ModelLinkedArtifactNames,
                        size_mb: float, readme: str | None,
                        user: User=User(name="GoonerMcGoon", is_admin=False)
    ) -> bool:
        if model_artifact.metadata.type != ArtifactType.model:
            return False

        if not DBAuditAccessor.append_audit(
            engine=self.engine,
            action=AuditAction.CREATE,
            user=user,
            metadata=model_artifact.metadata,
        ): return False

        db_model: DBModelSchema = DBArtifactSchema.from_artifact(model_artifact, size_mb).to_concrete()
        if not DBArtifactAccessor.artifact_insert(self.engine, db_model): return False
        DBConnectionAccessor.model_insert(self.engine, db_model, attached_names)

        if readme is not None:
            DBReadmeAccessor.artifact_insert_readme(self.engine, model_artifact, readme)

        return True

    def db_artifact_ingest(self, artifact: Artifact,
                        size_mb: float, readme: str | None,
                        user: User=User(name="GoonerMcGoon", is_admin=False)
    ) -> bool:
        if artifact.metadata.type == ArtifactType.model:
            return False

        if not DBAuditAccessor.append_audit(
            engine=self.engine,
            action=AuditAction.CREATE,
            user=user,
            metadata=artifact.metadata,
        ): return False

        db_model: DBArtifactSchema = DBArtifactSchema.from_artifact(artifact, size_mb)
        if not DBArtifactAccessor.artifact_insert(self.engine, db_model): return False
        DBConnectionAccessor.non_model_insert(self.engine, db_model)

        if readme is not None:
            DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, readme)

        return True

    def db_artifact_delete(self,
                           artifact_id: str,
                           artifact_type: ArtifactType,
                           user: User=User(name="GoonerMcGoon", is_admin=False)
    ):
        selected_artifact: DBArtifactSchema = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_id, artifact_type)
        if not selected_artifact:
            return False
        selected_artifact: Artifact = selected_artifact.to_artifact()

        if not DBAuditAccessor.append_audit(
            engine=self.engine,
            action=AuditAction.UPDATE,
            user=user,
            metadata=selected_artifact.metadata
        ): return False

        if not DBArtifactAccessor.artifact_delete(self.engine, selected_artifact.metadata.id, artifact_type): return False
        DBConnectionAccessor.connections_delete_by_artifact_id(self.engine, selected_artifact.metadata.id)

        DBReadmeAccessor.artifact_delete_readme(self.engine, artifact_id, artifact_type)

        return True

    def db_model_update(self,
        model: Artifact,
        new_size_mb: float, new_connections: ModelLinkedArtifactNames,
        new_readme: str | None,
        user: User=User(name="GoonerMcGoon", is_admin=False)
    ) -> bool:
        if model.metadata.type != ArtifactType.model:
            return False

        if not DBAuditAccessor.append_audit(
            engine=self.engine,
            action=AuditAction.UPDATE,
            user=user,
            metadata=model.metadata,
        ): return False

        query_model: DBModelSchema = DBModelSchema.from_artifact(model, new_size_mb).to_concrete()
        if not DBArtifactAccessor.artifact_update(self.engine, query_model): return False

        DBConnectionAccessor.connections_delete_by_artifact_id(self.engine, query_model.id)
        DBConnectionAccessor.model_insert(self.engine, query_model, new_connections)

        DBReadmeAccessor.artifact_delete_readme(self.engine, query_model.id, ArtifactType.model)
        if new_readme:
            DBReadmeAccessor.artifact_insert_readme(self.engine, model, new_readme)

        return True

    def db_artifact_update(self,
       artifact: Artifact,
       new_size_mb: float,
       new_readme: str | None,
       user: User = User(name="GoonerMcGoon", is_admin=False)
    ) -> bool:
        if artifact.metadata.type == ArtifactType.model:
            return False

        if not DBAuditAccessor.append_audit(
                engine=self.engine,
                action=AuditAction.UPDATE,
                user=user,
                metadata=artifact.metadata,
        ): return False

        query_artifact: DBArtifactSchema = DBModelSchema.from_artifact(artifact, new_size_mb).to_concrete()
        if not DBArtifactAccessor.artifact_update(self.engine, query_artifact): return False

        DBConnectionAccessor.connections_delete_by_artifact_id(self.engine, query_artifact.id)
        DBConnectionAccessor.non_model_insert(self.engine, query_artifact)

        DBReadmeAccessor.artifact_delete_readme(self.engine, query_artifact.id, query_artifact.type)
        if new_readme:
            DBReadmeAccessor.artifact_insert_readme(self.engine, artifact, new_readme)

        return True

    def db_artifact_get_query(self, query: ArtifactQuery, offset: str) -> list[ArtifactMetadata]|None:
        if len(query.types) == 0:
            query.types = [ArtifactType.model, ArtifactType.dataset, ArtifactType.code]
        results: list[DBArtifactSchema]|None = DBArtifactAccessor.artifact_get_by_query(self.engine, query, offset)
        if not results:
            return None

        return [artifact.to_artifact_metadata() for artifact in results]

    def db_artifact_get_id(self,
                           artifact_id: str,
                           artifact_type: ArtifactType,
                           user: User=User(name="GoonerMcGoon", is_admin=False)
    ) -> Artifact|None:
        result: None|DBArtifactSchema = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_id, artifact_type)
        if not result:
            return None

        result: Artifact = result.to_artifact()

        if not DBAuditAccessor.append_audit(
                engine=self.engine,
                action=AuditAction.DOWNLOAD,
                user=user,
                metadata=result.metadata
        ): return None

        return result

    def db_artifact_get_name(self, artifact_name: ArtifactName) -> list[ArtifactMetadata]|None:
        results: None|list[DBArtifactSchema] = DBArtifactAccessor.artifact_get_by_name(self.engine, artifact_name)
        if not results:
            return None

        return [result.to_artifact_metadata() for result in results]

    def db_artifact_get_regex(self, regex: ArtifactRegEx) -> list[ArtifactMetadata]|None:
        result, result_readme = DBArtifactAccessor.artifact_get_by_regex(self.engine, regex.regex)

        result_translated: list[ArtifactMetadata] = [result_artifact.to_artifact_metadata() for result_artifact in result]
        result_readme_translated: list[ArtifactMetadata] = [readme.to_artifact_metadata() for readme in result_readme]

        result_translated += result_readme_translated

        id_list: list[str] = []
        result: list[ArtifactMetadata] = []

        for result_val in result_translated:
            if result_val.id not in id_list:
                id_list.append(result_val.id)
                result.append(result_val)

        if not result:
            return None

        return result

    def db_artifact_exists(self, artifact_id: str, artifact_type: ArtifactType) -> bool:
        return DBArtifactAccessor.artifact_exists(self.engine, artifact_id, artifact_type)
    
    
class DBRouterAudit(DBRouterBase):
    def db_artifact_audit(self,
        artifact_type: ArtifactType,
        artifact_id: str,
        user: User=User(name="GoonerMcGoon", is_admin=False)
    ) -> None|list[ArtifactAuditEntry]:
        artifact: DBArtifactSchema|None = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_id, artifact_type)
        if not artifact:
            return None

        artifact: Artifact = artifact.to_artifact()

        audit_logs: list[ArtifactAuditEntry]|None = DBAuditAccessor.get_by_id(self.engine, ArtifactID(id=artifact_id), artifact_type)

        if not DBAuditAccessor.append_audit(
            self.engine,
            action=AuditAction.AUDIT,
            user=user,
            metadata=artifact.metadata,
        ): logger.error("Failed to append audit logs for get audit")

        return audit_logs


class DBRouterLineage(DBRouterBase):
    def db_model_connection_snapshot(self, model_id: str) -> ModelLinkedArtifactNames|None:
        model: DBArtifactSchema | None = DBArtifactAccessor.artifact_get_by_id(self.engine, model_id,
                                                                               ArtifactType.model)
        if not model:
            return None

        linked_names: ModelLinkedArtifactNames = ModelLinkedArtifactNames(
            linked_dset_names=[],
            linked_code_names=[],
            linked_parent_model_name="",
            linked_parent_model_relation="",
            linked_parent_model_rel_source=""
        )

        model: DBModelSchema = model.to_concrete()
        attached_artifacts = DBConnectionAccessor.model_get_associated_dset_and_code(self.engine, model)
        if not attached_artifacts:
            return linked_names

        for connection in attached_artifacts:
            if connection.relationship == DBConnectiveRelation.MODEL_DATASET:
                linked_names.linked_dset_names.append(connection.src_name)
            else:
                linked_names.linked_code_names.append(connection.src_name)

        parent_connection: DBConnectiveSchema = DBConnectionAccessor.model_get_parent_model(self.engine, model)
        if not parent_connection:
            return linked_names
        linked_names.linked_parent_model_name = parent_connection.src_name
        linked_names.linked_parent_model_relation = parent_connection.relationship_desc
        linked_names.linked_parent_model_rel_source = parent_connection.source_desc

        return linked_names


    def db_artifact_get_attached_datasets(self, model_id: str) -> list[Artifact]|None:
        model: DBArtifactSchema|None = DBArtifactAccessor.artifact_get_by_id(self.engine, model_id, ArtifactType.model)
        if not model:
            return None

        model: DBModelSchema = model.to_concrete()
        attached_artifacts = DBConnectionAccessor.model_get_associated_dset_and_code(self.engine, model)
        if not attached_artifacts:
            return None

        datasets: list[Artifact] = []
        for artifact_connection in attached_artifacts:
            if artifact_connection.relationship == DBConnectiveRelation.MODEL_DATASET:
                dataset: DBArtifactSchema = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_connection.src_id, ArtifactType.dataset)
                if dataset:
                    datasets.append(dataset.to_artifact())

        if not datasets:
            return None

        return datasets

    def db_artifact_get_attached_codebases(self, model_id: str) -> list[Artifact] | None:
        model: DBArtifactSchema | None = DBArtifactAccessor.artifact_get_by_id(self.engine, model_id,
                                                                               ArtifactType.model)
        if not model:
            return None

        model: DBModelSchema = model.to_concrete()
        attached_artifacts = DBConnectionAccessor.model_get_associated_dset_and_code(self.engine, model)
        if not attached_artifacts:
            return None

        codebases: list[Artifact] = []
        for artifact_connection in attached_artifacts:
            if artifact_connection.relationship == DBConnectiveRelation.MODEL_CODEBASE:
                codebase: DBArtifactSchema|None = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_connection.src_id,
                                                                      ArtifactType.code)
                if codebase:
                    codebases.append(codebase.to_artifact())

        if not codebases:
            return None

        return codebases

    def db_artifact_lineage(self,
        artifact_id: str
    ) -> ArtifactLineageGraph|None:
        artifact: DBArtifactSchema | None = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_id, ArtifactType.model)
        if not artifact:
            return None

        lineage_graph: ArtifactLineageGraph = ArtifactLineageGraph(
            nodes=[],
            edges=[]
        )

        selected_model: DBModelSchema|None = artifact.to_concrete()
        while selected_model:
            lineage_graph.nodes.append(ArtifactLineageNode(
                artifact_id=selected_model.id,
                name=selected_model.name,
                source="this_model",
                metadata={"url": str(artifact.url)}
            ))
            parent_model_relation = DBConnectionAccessor.model_get_parent_model(self.engine, selected_model)
            if parent_model_relation and parent_model_relation.src_id and parent_model_relation.dst_id:
                lineage_graph.edges.append(ArtifactLineageEdge(
                    from_node_artifact_id=parent_model_relation.src_id,
                    to_node_artifact_id=parent_model_relation.dst_id,
                    relationship=parent_model_relation.relationship_desc,
                ))
                selected_model = DBArtifactAccessor.artifact_get_by_id(self.engine, parent_model_relation.src_id,
                                                                       ArtifactType.model).to_concrete()
            else:
                selected_model = None

        return lineage_graph


class DBRouterCost(DBRouterBase):
    def db_artifact_cost(self,
        artifact_id: str,
        artifact_type: ArtifactType,
        dependency: bool
    ) -> ArtifactCost|None:

        artifact: DBArtifactSchema | None = DBArtifactAccessor.artifact_get_by_id(self.engine, artifact_id, artifact_type)
        if not artifact:
            return None

        cost: ArtifactCost = ArtifactCost(standalone_cost=artifact.size_mb, total_cost=artifact.size_mb)
        if not dependency or artifact_type != ArtifactType.model:
            return cost

        selected_model: DBModelSchema|None = artifact.to_concrete()

        while selected_model is not None:
            connections: list[DBConnectiveSchema] =  DBConnectionAccessor.model_get_associated_dset_and_code(self.engine, selected_model)
            for connection in connections:
                artifact: DBArtifactSchema = DBArtifactAccessor.artifact_get_by_id(
                    self.engine, connection.src_id, connection.relationship.to_source_type())
                if artifact:
                    cost.total_cost += artifact.size_mb
            parent_model_relation = DBConnectionAccessor.model_get_parent_model(self.engine, selected_model)
            if parent_model_relation:
                selected_model = DBArtifactAccessor.artifact_get_by_id(self.engine, parent_model_relation.src_id,
                                                                       ArtifactType.model)
                cost.total_cost += selected_model.size_mb
            else:
                selected_model = None

        return cost

class DBRouterRating(DBRouterBase):
    def db_rating_add(self,
        model_id: str,
        rating: BaseModelRating,
    ) -> bool:
        if not DBArtifactAccessor.artifact_get_by_id(self.engine, model_id, ArtifactType(rating.category)):
            return False

        return DBModelRatingAccessor.add_rating(self.engine, model_id, rating)

    def db_rating_get_snapshot(self, model_id: str) -> BaseModelRating|None:
        model_result: None | DBModelSchema = DBArtifactAccessor.artifact_get_by_id(self.engine, model_id,
                                                                                   ArtifactType.model)
        if not model_result:
            return None

        rating_result: DBModelRatingSchema = DBModelRatingAccessor.get_rating(self.engine, model_id)
        return rating_result.to_model_rating()

    def db_rating_get(self,
        model_id: str,
        user: User=User(name="GoonerMcGoon", is_admin=False)
    ) -> BaseModelRating|None:
        model_result: None|DBModelSchema = DBArtifactAccessor.artifact_get_by_id(self.engine, model_id, ArtifactType.model)
        if not model_result:
            return None

        rating_result: DBModelRatingSchema = DBModelRatingAccessor.get_rating(self.engine, model_id)
        if not rating_result:
            return None
        if not DBAuditAccessor.append_audit(
            self.engine,
            action=AuditAction.RATE,
            user=user,
            metadata=model_result.to_artifact_metadata(),
        ): logger.error("Failed to append audit logs for get rating")

        return rating_result.to_model_rating()

class DBManager:
    def __init__(self, engine: Engine):
        self.engine = engine
        SQLModel.metadata.create_all(self.engine)

        self.router_artifact: DBRouterArtifact = DBRouterArtifact(self.engine)
        self.router_audit: DBRouterAudit = DBRouterAudit(self.engine)
        self.router_lineage: DBRouterLineage = DBRouterLineage(self.engine)
        self.router_cost: DBRouterCost = DBRouterCost(self.engine)
        self.router_rating: DBRouterRating = DBRouterRating(self.engine)


    def db_reset(self):
        db_reset(self.engine)

    def db_get_snapshot_model(self, artifact_id: str) -> tuple[DBArtifactSchema, str, ModelLinkedArtifactNames, BaseModelRating]: # WHAT ABOUT WHEN SOMETHING THAT ANOTHER DEPENDS ON GETS UPDATED?
        artifact, readme = self.router_artifact.db_artifact_snapshot(artifact_id, ArtifactType.model)
        return artifact, readme, self.router_lineage.db_model_connection_snapshot(artifact_id), self.router_rating.db_rating_get_snapshot(artifact_id)

    def db_restore_snapshot_model(self, artifact: DBArtifactSchema, readme: str, names: ModelLinkedArtifactNames, rating: BaseModelRating):
        """
        TODO: Must add update to delete existing database entry to restore the snapshot. Also need separate endpoint for deleting model to prevent rating persistence
        """
        DBReadmeAccessor.artifact_insert_readme(self.engine, artifact.to_artifact(), readme)
        DBArtifactAccessor.artifact_insert(self.engine, artifact)
        DBConnectionAccessor.model_insert(self.engine, artifact.to_concrete(), names)
        DBModelRatingAccessor.add_rating(self.engine, artifact.id, rating)

    def db_get_snapshot_artifact(self, artifact_id: str, artifact_type: ArtifactType) -> tuple[DBArtifactSchema, str]:
        artifact, readme = self.router_artifact.db_artifact_snapshot(artifact_id, artifact_type)
        return artifact, readme


# TODO MUST ADD UPDATE