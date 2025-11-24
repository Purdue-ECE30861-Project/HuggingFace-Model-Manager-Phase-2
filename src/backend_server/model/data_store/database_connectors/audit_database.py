from __future__ import annotations

import hashlib
import json
import re
from typing import Optional
from typing import override, Dict, Any
from datetime import datetime

from huggingface_hub.utils.insecure_hashlib import sha256
from pydantic import HttpUrl
from pydantic_core import ValidationError
from sqlalchemy import Dialect
from sqlalchemy import Engine, JSON
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.sql import expression
from sqlalchemy.types import TypeDecorator, String, Text
from sqlmodel import Field, SQLModel, Session, create_engine, select  # pyright: ignore[reportUnknownVariableType]
from typing_extensions import Literal

from src.backend_server.model.data_store.database_connectors.base_database import DBAccessorBase
from src.backend_server.model.data_store.database_connectors.database_schemas import ArtifactAuditSchemaDB
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactQuery, ArtifactType, ArtifactData, \
    ArtifactName, ArtifactID
from src.contracts.model_rating import ModelRating
from src.contracts.auth_contracts import User, AuditAction, ArtifactAuditEntry
import logging
from src.backend_server.model.data_store.db_utils import *


logger = logging.getLogger(__name__)


class SQLAuditAccessor(DBAccessorBase): # I assume we use separate tables for cost, lineage, etc
    def append_audit(self, action: AuditAction, user: User, metadata: ArtifactMetadata) -> bool:
        audit_value = ArtifactAuditSchemaDB.generate_from_information(
            metadata,
            user,
            action,
            datetime.now()
        )

        with Session(self.engine) as session:
            try:
                session.add(audit_value)
                session.commit()
                return True
            except Exception as e:
                logger.error(e)
                return False

    def get_by_id(self, id: ArtifactID, artifact_type: ArtifactType) -> list[ArtifactAuditEntry]|None:
        with Session(self.engine) as session:
            query = select(ArtifactAuditSchemaDB).where(
                ArtifactAuditSchemaDB.id == id.id,
                ArtifactAuditSchemaDB.artifact_type == artifact_type
            )
            result = session.exec(query).all()
            result_reformatted = [entry.to_audit_entry() for entry in result]

            if not result_reformatted:
                return None
            return result_reformatted


