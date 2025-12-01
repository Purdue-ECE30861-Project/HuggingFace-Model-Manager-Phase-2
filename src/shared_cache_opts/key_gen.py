import hashlib
from fastapi import Request

async def make_deterministic_request_key(request: Request) -> str:
    """
    Deterministic key based ONLY on:
    - HTTP method
    - URL path
    - Sorted query params
    - Request body (bytes)
    """
    body = await request.body()

    deterministic_str = (
        f"method={request.method}\n"
        f"path={request.url.path}\n"
        f"query={sorted(request.query_params.multi_items())}\n"
        f"body={body.decode('utf-8', errors='ignore')}"
    )

    return hashlib.sha256(deterministic_str.encode("utf-8")).hexdigest()