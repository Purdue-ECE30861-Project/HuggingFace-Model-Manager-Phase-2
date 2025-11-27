import inspect
from fastapi import Request, Response
from functools import wraps

from src.backend_server.global_state import cache_accessor
from src.contracts.artifact_contracts import ArtifactType
from src.shared_cache_opts.key_gen import make_deterministic_request_key


def cache_response(save_on_status: int):
    """
    Decorator for FastAPI endpoints.

    Requirements:
    - Endpoint MUST have parameters: (request: Request, artifact_id: str)
    - On specific status code, cache the returned model using cache_accessor.
    """

    def decorator(func):
        sig = inspect.signature(func)

        # ensure required parameters exist
        if "request" not in sig.parameters:
            raise TypeError("Endpoint decorated with @cache_response must have a 'request: Request' parameter")
        if "artifact_id" not in sig.parameters:
            raise TypeError("Endpoint decorated with @cache_response must have an 'artifact_id: str' parameter")
        if "artifact_type" not in sig.parameters:
            raise TypeError("Endpoint decorated with @cache_response must have a 'artifact_type: ArtifactType' parameter")

        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get("request")
            artifact_id: str = kwargs.get("artifact_id")
            artifact_type: ArtifactType = kwargs.get("artifact_type")

            if request is None or artifact_id is None or artifact_type is None:
                raise TypeError("Decorator requires 'request' and 'artifact_id' parameters to be passed")

            # Run endpoint
            result = await func(*args, **kwargs)

            # Allow returning Response objects, OR pydantic models
            if isinstance(result, Response):
                status_code = result.status_code
            else:
                # FastAPI generally infers status_code via route decorator; assume 200 fallback
                raise Exception("What the fuck happened? Go fuck yourself")

            # Only cache if status matches
            if status_code == save_on_status:
                request_hash = await make_deterministic_request_key(request)

                # Must be BaseModel for cache_accessor.insert()
                if hasattr(result, "model_dump_json"):
                    serialized_model = result.model_dump_json()
                elif hasattr(result, "to_json"):
                    serialized_model = result.to_json()
                else:
                    # If you want to enforce only BaseModel outputs:
                    raise TypeError("Endpoint return must be a Pydantic BaseModel to be cached")

                cache_accessor.insert(
                    artifact_id=artifact_id,
                    artifact_type=artifact_type,
                    request=request_hash,
                    response=serialized_model,
                )

            # Always return the original result unchanged
            return result

        return wrapper

    return decorator