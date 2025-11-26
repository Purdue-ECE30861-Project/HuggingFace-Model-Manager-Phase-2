from __future__ import annotations

import logging

from sqlalchemy import Engine, select
from sqlmodel import Session  # pyright: ignore[reportUnknownVariableType]

from .database_schemas import DBModelRatingSchema
from .serializers import *

logger = logging.getLogger(__name__)


class DBModelRatingAccessor:
    @staticmethod
    def get_rating(engine: Engine, model_id: str) -> None|DBModelRatingSchema:
        result: DBModelRatingSchema|None = None
        with Session(engine) as session:
            query = select(DBModelRatingSchema).where(DBModelRatingSchema.id == model_id)
            result: DBModelRatingSchema = session.exec(query).first()
        if not result:
            return None

        return result[0]

    @staticmethod
    def add_rating(engine: Engine, model_id: str, rating: ModelRating) -> bool:
        with Session(engine) as session:
            try:
                session.add(DBModelRatingSchema(id=model_id, rating=rating))
                session.commit()
            except Exception as e:
                logger.error(e)
                return False
        return True

    @staticmethod
    def delete_rating(engine: Engine, model_id: str) -> bool:
        with Session(engine) as session:
            try:
                query = select(DBModelRatingSchema).where(DBModelRatingSchema.id == model_id)
                result = session.exec(query).first()
                session.delete(result)
                session.commit()
            except Exception as e:
                logger.error(e)
                return False
        return True
