from __future__ import annotations
from src.contracts.artifact_contracts import Artifact, ArtifactMetadata, ArtifactQuery, ArtifactType, ArtifactData
from src.contracts.model_rating import ModelRating
from sqlmodel import Field, SQLModel, Session, create_engine, select # pyright: ignore[reportUnknownVariableType]
from sqlalchemy import Engine, JSON
from sqlalchemy.orm.attributes import flag_modified
from typing_extensions import Literal
from pydantic import HttpUrl
from sqlalchemy.types import TypeDecorator, String, Text
from sqlalchemy import Dialect
from sqlalchemy.sql import expression
from sqlalchemy.ext.compiler import compiles
from typing import Any, Optional


class JsonExtract(expression.FunctionElement[str]):
    inherit_cache=True
    name = 'json_extract'
    type = Text()

@compiles(JsonExtract, 'sqlite')
def _json_extract_sqlite(element: JsonExtract, compiler: Any, **kw: Any) -> str: # pyright: ignore[reportUnusedFunction]
    return "json_extract(%s)" % compiler.process(element.clauses, **kw)

@compiles(JsonExtract, 'mysql')
def _json_extract_mysql(element: JsonExtract, compiler: Any, **kw: Any) -> str: # pyright: ignore[reportUnusedFunction]
    return "json_extract(%s)" % compiler.process(element.clauses, **kw)

@compiles(JsonExtract, 'postgresql')
def _json_extract_postgres(element: JsonExtract, compiler: Any, **kw: Any) -> str: # pyright: ignore[reportUnusedFunction]
    args = list(element.clauses)
    return "%s #>> '{%s}'" % (
        compiler.process(args[0], **kw),
        args[1].value[2:].replace(".", ",")  # Convert $.path.to.field to path,to,field
    )

from pydantic_core import ValidationError
import re
import json
from typing import override, Dict, Any

class HttpUrlSerializer(TypeDecorator[HttpUrl|None]):
    impl = String(2083)
    cache_ok = True
    
    @override
    def process_bind_param(self, value: HttpUrl | None, dialect: Dialect) -> str:
        return str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> HttpUrl|None:
        if value is None:
            return None
        try:
            return HttpUrl(url=value)
        except ValidationError:
            return None

    def process_literal_param(self, value: HttpUrl | None, dialect: Dialect) -> str:
        return str(value)


class ModelRatingSerializer(TypeDecorator[ModelRating]):
    impl = JSON
    cache_ok = True

    @override
    def process_bind_param(self, value: ModelRating | None, dialect: Dialect) -> Dict[str, Any] | None:
        if value is None:
            return None
        return value.model_dump()

    def process_result_value(self, value: Dict[str, Any] | None, dialect: Dialect) -> ModelRating | None:
        if value is None:
            return None
        return ModelRating.model_validate(value)

    def process_literal_param(self, value: ModelRating | None, dialect: Dialect) -> str:
        if value is None:
            return ""
        return json.dumps(value.model_dump())


class ArtifactDataDB(SQLModel, table=True): # what about for storage of datasets? Do they themselves have 'ModelRating?' Must consider this for future iteration
    id: str = Field(default="BoatyMcBoatFace", primary_key=True)
    url: HttpUrl = Field(sa_type=HttpUrlSerializer)
    rating: ModelRating = Field(sa_type=ModelRatingSerializer)

    @staticmethod
    def create_db_artifact(id: str, url: HttpUrl, rating: ModelRating):
        return ArtifactDataDB(id=id, url=url, rating=rating)

    @staticmethod
    def create_from_artifact(artifact: Artifact, rating: Optional[ModelRating]):
        return ArtifactDataDB(
            id=artifact.metadata.id,
            url=artifact.data.url,
            rating=rating
        )

    def update_from_artifact(self, artifact: Artifact):
        self.rating.name = artifact.metadata.name
        flag_modified(self, "rating")
        self.url = HttpUrl(artifact.data.url)

    def generate_metadata(self) -> ArtifactMetadata:
        return ArtifactMetadata(
            name=self.rating.name,
            id=str(self.id),
            type=ArtifactType(self.rating.category)
        )

   # def generate_artifact_data(self) -> ArtifactDataDB:



class SQLMetadataAccessor: # I assume we use separate tables for cost, lineage, etc
    db_url: str | Literal["sqlite+pysqlite:///:memory:"] = "sqlite+pysqlite:///:memory:"
    schema: ArtifactDataDB
    engine: Engine
    
    def __init__(self, db_url: str|None = None) -> None:
        if db_url is not None:
            self.db_url = db_url
        self.engine = create_engine(self.db_url)
        SQLModel.metadata.create_all(self.engine)
    
    def add_to_db(self, artifact: ArtifactDataDB) -> bool: # return false if in DB already
        try:
            if self.is_in_db(artifact.rating.name, ArtifactType(artifact.rating.category)):
                return False
            with Session(self.engine) as session:
                session.add(artifact)
                session.commit()
            return True
        except Exception as e:
            return False

    def reset_db(self) -> bool:
        """
        Reset the database by deleting all data from all tables.
        Returns True if successful, False if an error occurred.
        """
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
        search = re.compile(regex)
        artifacts = self.get_all()
        if artifacts is None:
            return None
        return list(filter(lambda artifact: search.match(artifact.rating.name) is not None, artifacts))

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