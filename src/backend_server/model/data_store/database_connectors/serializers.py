import json
from typing import override, Dict, Any

from pydantic import ValidationError, HttpUrl
from sqlalchemy import TypeDecorator, String, Dialect, JSON

from src.contracts.auth_contracts import User
from src.contracts.model_rating import ModelRating


class UserSerializer(TypeDecorator[User | None]):
    impl = String(2083)
    cache_ok = True

    @override
    def process_bind_param(self, value: User | None, dialect: Dialect) -> str:
        return value.model_dump_json()

    def process_result_value(self, value: str | None, dialect: Dialect) -> User | None:
        if value is None:
            return None
        try:
            return User.model_validate_json(value)
        except ValidationError:
            return None

    def process_literal_param(self, value: User | None, dialect: Dialect) -> str:
        return value.model_dump_json()


class HttpUrlSerializer(TypeDecorator[HttpUrl | None]):
    impl = String(2083)
    cache_ok = True

    @override
    def process_bind_param(self, value: HttpUrl | None, dialect: Dialect) -> str:
        return str(value)

    def process_result_value(self, value: str | None, dialect: Dialect) -> HttpUrl | None:
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