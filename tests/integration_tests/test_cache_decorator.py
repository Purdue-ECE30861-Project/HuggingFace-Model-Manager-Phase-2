import unittest
import logging
import asyncio
from typing import Any, Dict, List, Tuple

from fastapi import Request, Response
from pydantic import BaseModel

from src.backend_server.model.data_store.cache_decorator import cache_response
from src.contracts.artifact_contracts import ArtifactType
from src.shared_cache_opts import key_gen
from src.backend_server import global_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FakeCachedModel(BaseModel):
    data: str

    # Provide a to_json method compatible with CacheAccessor expectations
    def to_json(self) -> str:
        return self.model_dump_json()


class FakeCacheAccessor:
    """
    Simple stand-in for global_state.cache_accessor to capture insert calls.
    """

    def __init__(self) -> None:
        self.inserts: List[Tuple[str, ArtifactType, str, Any]] = []

    def insert(self, artifact_id: str, artifact_type: ArtifactType, request: str, response: BaseModel) -> bool:
        self.inserts.append((artifact_id, artifact_type, request, response))
        return True


async def make_dummy_request(
    method: str = "GET",
    path: str = "/dummy",
    query: str = "",
    body: bytes = b"",
) -> Request:
    """
    Construct a minimal FastAPI Request for testing.
    """
    scope: Dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode("utf-8"),
        "headers": [],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }

    async def receive() -> Dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


class TestCacheDecorator(unittest.IsolatedAsyncioTestCase):
    """
    Async test case for cache_response decorator behavior.
    """

    async def asyncSetUp(self):
        # Patch global_state.cache_accessor with a fake
        self.original_cache_accessor = global_state.cache_accessor
        self.fake_cache = FakeCacheAccessor()
        global_state.cache_accessor = self.fake_cache

        # Patch make_deterministic_request_key to a deterministic constant
        self.original_key_gen = key_gen.make_deterministic_request_key

        async def fake_key(request: Request) -> str:
            return "fixed-hash-for-test"

        key_gen.make_deterministic_request_key = fake_key  # type: ignore[assignment]

    async def asyncTearDown(self):
        # Restore patches
        global_state.cache_accessor = self.original_cache_accessor
        key_gen.make_deterministic_request_key = self.original_key_gen  # type: ignore[assignment]

    async def test_cache_response_happy_path_saves_on_matching_status(self):
        """
        When endpoint returns a Response-like object with correct status,
        the decorator should call cache_accessor.insert with proper arguments.
        """

        @cache_response(save_on_status=200)
        async def endpoint(
            request: Request,
            artifact_id: str,
            artifact_type: ArtifactType,
        ):
            # Return a Response subclass that also behaves like a model with .to_json
            class CachedResponse(Response):
                def __init__(self, content: str):
                    super().__init__(content=content, media_type="application/json")
                    self._model = FakeCachedModel(data=content)

                def to_json(self) -> str:  # used by cache_decorator
                    return self._model.to_json()

            return CachedResponse('{"hello": "world"}')

        req = await make_dummy_request()
        artifact_id = "cache-deco-1"
        artifact_type = ArtifactType.model

        result = await endpoint(
            request=req,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
        )

        # Returned object should be passed through unchanged
        self.assertIsInstance(result, Response)

        # Exactly one insert call should have happened
        self.assertEqual(len(self.fake_cache.inserts), 1)
        ins_artifact_id, ins_type, ins_request, ins_response = self.fake_cache.inserts[0]

        self.assertEqual(ins_artifact_id, artifact_id)
        self.assertEqual(ins_type, artifact_type)
        self.assertEqual(ins_request, "fixed-hash-for-test")
        # Response object itself should be passed through
        self.assertIs(ins_response, result)

    async def test_cache_response_does_not_cache_on_non_matching_status(self):
        """
        If the status code does not match save_on_status, no cache write occurs.
        """

        @cache_response(save_on_status=200)
        async def endpoint(
            request: Request,
            artifact_id: str,
            artifact_type: ArtifactType,
        ):
            return Response(content="no-cache", status_code=404)

        req = await make_dummy_request()
        await endpoint(
            request=req,
            artifact_id="cache-deco-2",
            artifact_type=ArtifactType.dataset,
        )

        self.assertEqual(len(self.fake_cache.inserts), 0)

    async def test_cache_response_requires_required_parameters(self):
        """
        Decorator should enforce presence of request, artifact_id, artifact_type in signature.
        """

        # Missing artifact_id in signature
        with self.assertRaises(TypeError):

            @cache_response(save_on_status=200)
            async def bad_endpoint_missing_artifact_id(
                request: Request,
                artifact_type: ArtifactType,
            ):
                return Response(content="ok")

        # Missing request in signature
        with self.assertRaises(TypeError):

            @cache_response(save_on_status=200)
            async def bad_endpoint_missing_request(
                artifact_id: str,
                artifact_type: ArtifactType,
            ):
                return Response(content="ok")

        # Missing artifact_type in signature
        with self.assertRaises(TypeError):

            @cache_response(save_on_status=200)
            async def bad_endpoint_missing_artifact_type(
                request: Request,
                artifact_id: str,
            ):
                return Response(content="ok")

    async def test_cache_response_raises_if_request_or_artifact_missing_at_call(self):
        """
        If wrapper is called without required kwargs, it should raise TypeError.
        """

        @cache_response(save_on_status=200)
        async def endpoint(
            request: Request,
            artifact_id: str,
            artifact_type: ArtifactType,
        ):
            return Response(content="ok")

        # Call without required kwargs
        with self.assertRaises(TypeError):
            await endpoint()  # type: ignore[call-arg]


if __name__ == "__main__":
    # Needed because we used IsolatedAsyncioTestCase
    unittest.main()
