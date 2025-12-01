from __future__ import annotations

import json
import re
from typing import Optional
from typing import override, Dict, Any
from datetime import datetime

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

from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactQuery, ArtifactType, ArtifactData, \
    ArtifactID
from src.contracts.model_rating import ModelRating
from src.contracts.auth_contracts import User, AuditAction, ArtifactAuditEntry
import logging


logger = logging.getLogger(__name__)


class JsonExtract(expression.FunctionElement[str]):
    inherit_cache = True
    name = 'json_extract'
    type = Text()


@compiles(JsonExtract, 'sqlite')
def _json_extract_sqlite(element: JsonExtract, compiler: Any,
                         **kw: Any) -> str:  # pyright: ignore[reportUnusedFunction]
    return "json_extract(%s)" % compiler.process(element.clauses, **kw)


@compiles(JsonExtract, 'mysql')
def _json_extract_mysql(element: JsonExtract, compiler: Any, **kw: Any) -> str:  # pyright: ignore[reportUnusedFunction]
    return "json_extract(%s)" % compiler.process(element.clauses, **kw)


@compiles(JsonExtract, 'postgresql')
def _json_extract_postgres(element: JsonExtract, compiler: Any,
                           **kw: Any) -> str:  # pyright: ignore[reportUnusedFunction]
    args = list(element.clauses)
    return "%s #>> '{%s}'" % (
        compiler.process(args[0], **kw),
        args[1].value[2:].replace(".", ",")  # Convert $.path.to.field to path,to,field
    )


class ArtifactAuditSchemaDB(SQLModel, table=True):
    id: str = Field(default="Python have me goonin", primary_key=True)
    artifact_type: ArtifactType
    name: str
    user: User
    date: datetime
    action: AuditAction

    @staticmethod
    def generate_from_information(metadata: ArtifactMetadata, user: User, action: AuditAction, time: datetime) -> "ArtifactAuditSchemaDB":
        return ArtifactAuditSchemaDB (
            id=metadata.id,
            artifact_type=metadata.type,
            name=metadata.name,
            user=user,
            action=action,
            date=time
        )

    def to_audit_entry(self) -> ArtifactAuditEntry:
        return ArtifactAuditEntry(
            user=self.user,
            date=self.date,
            artifact=ArtifactMetadata(
                id=self.id,
                name=self.name.name,
                type=self.artifact_type
            ),
            action=self.action
        )


class SQLAuditAccessor: # I assume we use separate tables for cost, lineage, etc
    db_url: str | Literal["sqlite+pysqlite:///:memory:"] = "sqlite+pysqlite:///:memory:"
    schema: ArtifactAuditSchemaDB
    engine: Engine

    def __init__(self, db_url: str|None = None) -> None:
        if db_url is not None:
            self.db_url = db_url
        self.engine = create_engine(self.db_url)
        SQLModel.metadata.create_all(self.engine)

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

    def reset_db(self):
        try:
            with Session(self.engine) as session:
                # Get all table objects from SQLModel metadata
                tables = SQLModel.metadata.tables.values()

                # Delete all data from each table in reverse dependency order
                # This helps avoid foreign key constraint issues
                for table in reversed(list(tables)):
                    session.exec(table.delete())

                session.commit()
                return True

        except Exception as e:
            # Log the error if you have logging set up
            # logger.error(f"Failed to reset database: {e}")
            return False

