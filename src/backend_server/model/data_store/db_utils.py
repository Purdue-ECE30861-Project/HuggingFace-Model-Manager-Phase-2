from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression
from sqlalchemy.types import Text

logger = logging.getLogger(__name__)


class JsonExtract(expression.FunctionElement[str]):
    inherit_cache=True
    name = 'json_extract'
    type = Text()

@compiles(JsonExtract, 'sqlite')
def json_extract_sqlite(element: JsonExtract, compiler: Any, **kw: Any) -> str: # pyright: ignore[reportUnusedFunction]
    return "json_extract(%s)" % compiler.process(element.clauses, **kw)

@compiles(JsonExtract, 'mysql')
def json_extract_mysql(element: JsonExtract, compiler: Any, **kw: Any) -> str: # pyright: ignore[reportUnusedFunction]
    return "json_extract(%s)" % compiler.process(element.clauses, **kw)

@compiles(JsonExtract, 'postgresql')
def json_extract_postgres(element: JsonExtract, compiler: Any, **kw: Any) -> str: # pyright: ignore[reportUnusedFunction]
    args = list(element.clauses)
    return "%s #>> '{%s}'" % (
        compiler.process(args[0], **kw),
        args[1].value[2:].replace(".", ",")  # Convert $.path.to.field to path,to,field
    )