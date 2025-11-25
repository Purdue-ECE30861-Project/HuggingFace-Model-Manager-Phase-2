from __future__ import annotations

from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Session, select  # pyright: ignore[reportUnknownVariableType]

from src.backend_server.model.data_store.database_connectors.database_schemas import ArtifactAuditSchemaDB
from src.backend_server.model.data_store.db_utils import *
from src.contracts.artifact_contracts import ArtifactMetadata, ArtifactType, ArtifactID
from src.contracts.auth_contracts import User, AuditAction, ArtifactAuditEntry

logger = logging.getLogger(__name__)


class DBAuditAccessor: # I assume we use separate tables for cost, lineage, etc
    @staticmethod
    def append_audit(engine: Engine, action: AuditAction, user: User, metadata: ArtifactMetadata) -> bool:
        audit_value = ArtifactAuditSchemaDB.generate_from_information(
            metadata,
            user,
            action,
            datetime.now()
        )

        with Session(engine) as session:
            try:
                session.add(audit_value)
                session.commit()
                return True
            except Exception as e:
                logger.error(e)
                return False

    @staticmethod
    def get_by_id(engine: Engine, id: ArtifactID, artifact_type: ArtifactType) -> list[ArtifactAuditEntry]|None:
        with Session(engine) as session:
            query = select(ArtifactAuditSchemaDB).where(
                ArtifactAuditSchemaDB.id == id.id,
                ArtifactAuditSchemaDB.artifact_type == artifact_type
            )
            result = session.exec(query).all()
            result_reformatted = [entry.to_audit_entry() for entry in result]

            if not result_reformatted:
                return None
            return result_reformatted


