from __future__ import annotations
from src.controller.api_types import ModelRating
from sqlmodel import Field, SQLModel, Session, create_engine, select # pyright: ignore[reportUnknownVariableType]
from sqlalchemy import Engine;
from typing_extensions import Literal
from pydantic import HttpUrl
import re

class ModelData(SQLModel):
    id: int | None = Field(default=None, primary_key=True)
    model_url: HttpUrl
    dataset_url: HttpUrl
    codebase_url: HttpUrl
    rating: ModelRating


class SQLAccessor():

    db_url: str | Literal["sqlite+pysqlite:///:memory:"]
    schema: ModelData
    engine: Engine
    
    def __init__(self, db_url: str|None = None) -> None:
        if db_url is not None:
            self.db_url = db_url
        self.engine = create_engine(self.db_url)
        SQLModel.metadata.create_all(self.engine)
    
    def add_to_db(self, model: ModelData):
        session = Session(self.engine)
        session.add(model)
        session.close()
    
    def is_in_db(self, model_name: str) -> bool:
        with Session(self.engine) as session:
            selection = select(ModelData).where(ModelData.rating.name == model_name)
            return len(session.exec(selection).fetchall()) > 0
    
    def get_by_name(self, model_name: str) -> ModelData|None:
        with Session(self.engine) as session:
            selection = select(ModelData).where(ModelData.rating.name == model_name)
            model = session.exec(selection)
            return model.first()
    
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
                
        