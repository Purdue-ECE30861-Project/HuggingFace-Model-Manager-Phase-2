import re
from fastapi import HTTPException, FastAPI, Request
from fastapi.exceptions import RequestValidationError

VALIDATION_ERROR_MESSAGE_LOOKUP: dict[tuple[str, str], str] = {
    ("POST", "/artifacts"):"There is missing field(s) in the artifact_query or it is formed improperly, or is invalid.",
    ("GET", "/artifacts/*/*"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid.",
    ("DELETE", "/artifacts/*/*"):"There is missing field(s) in the artifact_type or artifact_id or invalid",
    ("PUT", "/artifact/*/*"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid.",
    ("GET", "/artifact/model/*/rate"):"There is missing field(s) in the artifact_id or it is formed improperly, or is invalid.",
    ("POST", "/artifact/*"):"There is missing field(s) in the artifact_data or it is formed improperly (must include a single url).",
    ("GET", "/artifact/*/*/cost"):"There is missing field(s) in the artifact_type or artifact_id or it is formed improperly, or is invalid."
}

def get_validation_error_message(key: tuple[str, str]) -> str:
    exact_match = VALIDATION_ERROR_MESSAGE_LOOKUP.get(key)
    if exact_match is not None:
        return exact_match
    for (m, p), message in VALIDATION_ERROR_MESSAGE_LOOKUP.items():
        if m != key[0]:
            continue
        # Convert wildcard '*' to regex
        pattern = "^" + re.escape(p).replace("\\*", "[^/]+") + "$"
        if re.match(pattern, key[1]):
            return message

    return "Bad Format"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        raise HTTPException(
            status_code=400,
            detail=get_validation_error_message((request.method, request.url.path)),
        )