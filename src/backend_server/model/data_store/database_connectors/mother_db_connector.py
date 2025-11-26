import logging

from sqlalchemy import Engine

from src.contracts.artifact_contracts import ArtifactQuery, ArtifactName, ArtifactRegEx, ArtifactID, \
    ArtifactLineageGraph, ArtifactCost
from .database_schemas import *
from .audit_database import DBAuditAccessor
from .artifact_database import DBArtifactAccessor, DBConnectionAccessor, DBReadmeAccessor
from .model_rating_database import DBModelRatingAccessor
from .base_database import db_reset


logger = logging.getLogger(__name__)


class DBRouterBase:
    def __init__(self, engine: Engine):
        self.engine = engine


class DBRouterArtifact(DBRouterBase):
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

        db_model: DBModelSchema = DBArtifactSchema.from_artifact(model_artifact, size_mb)
        if not DBArtifactAccessor.artifact_insert(self.engine, db_model): return False
        DBConnectionAccessor.model_insert(self.engine, db_model, attached_names)

        if readme is not None:
            DBReadmeAccessor.artifact_insert_readme(self.engine, model_artifact, readme)

        return True

    def db_model_add_rating(self, model_id: str, rating: ModelRating) -> bool:
        if not DBArtifactAccessor.artifact_exists(self.engine, model_id, ArtifactType.model):
            return False
        DBModelRatingAccessor.add_rating(self.engine, model_id, rating)
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

        if not DBArtifactAccessor.artifact_delete(self.engine, selected_artifact.id, artifact_type): return False
        DBConnectionAccessor.connections_delete_by_artifact_id(self.engine, selected_artifact.id)

        DBReadmeAccessor.artifact_delete_readme(self.engine, artifact_id, artifact_type)

        return True

    # def db_model_update(self, artifact: Artifact, new_size_mb: float, new_connections: ):
    #     if not DBAuditAccessor.append_audit(
    #         engine=self.engine,
    #         action=AuditAction.UPDATE,
    #     )
    #     raise NotImplementedError()

    def db_artifact_get_query(self, query: ArtifactQuery, offset: str) -> list[ArtifactMetadata]|None:
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
        result, result_readme = DBArtifactAccessor.artifact_get_by_regex(self.engine, regex)

        result_translated = set([result_artifact.to_artifact_metadata() for result_artifact in result])
        result_readme_translated = set([readme.to_metadata() for readme in result_readme])
        result = list(result_translated.union(result_readme_translated))

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

        raise NotImplementedError()

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

        selected_model: DBModelSchema|None = artifact

        while selected_model is not None:
            connections: list[DBConnectiveSchema] =  DBConnectionAccessor.model_get_associated_dset_and_code(self.engine, selected_model)
            for connection in connections:
                artifact: DBArtifactSchema = DBArtifactAccessor.artifact_get_by_id(
                    self.engine, connection.src_id, connection.relationship.to_source_type())
                cost.total_cost += artifact.size_mb
            parent_model_relation = DBConnectionAccessor.model_get_parent_model(self.engine, selected_model)
            selected_model = DBArtifactAccessor.artifact_get_by_id(self.engine, parent_model_relation.src_id, ArtifactType.model)

        return selected_model

class DBRouterRating(DBRouterBase):
    def db_rating_add(self,
        model_id: str,
        rating: ModelRating
    ) -> bool:
        if not DBArtifactAccessor.artifact_get_by_id(self.engine, model_id, ArtifactType(rating.category)):
            return False

        return DBModelRatingAccessor.add_rating(self.engine, model_id, rating)

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
        self.db_reset()


# TODO MUST ADD UPDATE