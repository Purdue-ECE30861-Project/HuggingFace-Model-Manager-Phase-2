from __future__ import annotations
from src.external_contracts import ModelRating, Artifact, ArtifactMetadata, ArtifactQuery, ArtifactType
from sqlmodel import Field, SQLModel, Session, create_engine, select # pyright: ignore[reportUnknownVariableType]
from sqlalchemy import Engine, JSON;
from typing_extensions import Literal
from pydantic import HttpUrl
from sqlalchemy.types import TypeDecorator, String, Text
from sqlalchemy import Dialect
from sqlalchemy.sql import expression
from sqlalchemy.ext.compiler import compiles
from typing import Any

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


class ModelData(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    model_url: HttpUrl = Field(sa_type=HttpUrlSerializer)
    dataset_url: HttpUrl | None = Field(sa_type=HttpUrlSerializer)
    codebase_url: HttpUrl | None = Field(sa_type=HttpUrlSerializer)
    rating: ModelRating = Field(sa_type=ModelRatingSerializer)


class SQLMetadataAccessor: # I assume we use separate tables for cost, lineage, etc
    db_url: str | Literal["sqlite+pysqlite:///:memory:"] = "sqlite+pysqlite:///:memory:"
    schema: ModelData
    engine: Engine
    
    def __init__(self, db_url: str|None = None) -> None:
        if db_url is not None:
            self.db_url = db_url
        self.engine = create_engine(self.db_url)
        SQLModel.metadata.create_all(self.engine)
    
    def add_to_db(self, model: ModelData):
        with Session(self.engine) as session:
            session.add(model)
            session.commit()
    
    def is_in_db(self, model_name: str) -> bool:
        with Session(self.engine) as session:
            # Use our database-agnostic JSON extraction
            query = select(ModelData).where(
                JsonExtract(ModelData.rating, '$.name') == model_name
            )
            return session.exec(query).first() is not None
    
    def get_by_name(self, model_name: str) -> ModelData|None:
        with Session(self.engine) as session:
            # Use our database-agnostic JSON extraction
            query = select(ModelData).where(
                JsonExtract(ModelData.rating, '$.name') == model_name
            )
            return session.exec(query).first()
    
    def get_all(self) -> list[ModelData]|None:
        with Session(self.engine) as session:
            selection = select(ModelData)
            model = session.exec(selection)
            return list(model.fetchall())

    def get_by_regex(self, regex: str) -> list[ModelData]|None:
        search = re.compile(regex)
        models = self.get_all()
        if models is None:
            return None
        return list(filter(lambda model: search.match(model.rating.name) is not None, models))

    def get_by_query(self, query: ArtifactQuery, offset: str) -> list[ArtifactMetadata]|None: # return NONE if there are TOO MANY artifacts. If no matches return empty list. This endpoint does not call for not found errors
        raise NotImplementedError()

    def get_by_id(self, id: str, artifact_type: ArtifactType) -> Artifact|None:
        raise NotImplementedError()
                
    def update_artifact(self, id: str, updated: Artifact, artifact_type: ArtifactType) -> bool: # should return false if the artifact is not found
        raise NotImplementedError()

    def delete_artifact(self, id: str, artifact_type: ArtifactType) -> bool: # return false if artifact is not found
        raise NotImplementedError()