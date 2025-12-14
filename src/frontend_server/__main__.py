from fastapi import FastAPI
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.requests import Request
from fastapi.responses import JSONResponse
import os
import logging
import redis
import json
import hashlib
import base64
import asyncio
from typing import Optional, Dict, Any
from src.frontend_server import BACKEND_CONFIG

from src.frontend_server.controller.health import health_router
from src.frontend_server.controller.webpage import webpage_router
from fastapi.staticfiles import StaticFiles
from os import getenv
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


class CacheRouter:
    """
    Redis-based cache router for API responses.
    """

    def __init__(
        self,
        password: str = "",
        host: str = "172.31.10.22",
        port: int = 6379,
        db: int = 0,
        default_ttl: int = 3600,
    ):
        self.default_ttl = default_ttl
        self.redis_client = None

        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )

            self.redis_client.ping()
            logger.info(f"Redis cache connected successfully at {host}:{port}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching disabled.")
            self.redis_client = None

    def is_available(self) -> bool:
        """
        Check if Redis is available
        """
        return self.redis_client is not None

    @staticmethod
    def _filter_headers_for_caching(headers: Dict[str, str]) -> Dict[str, str]:
        """
        Filter out sensitive and hop-by-hop headers before caching.

        Removes headers that should not be cached or forwarded:
        - Set-Cookie, Authorization, Proxy-Authorization
        - Hop-by-hop headers (Connection, Transfer-Encoding, etc.)
        - Content-Length (may change when reconstructed)
        """
        excluded = {
            "set-cookie",
            "authorization",
            "proxy-authorization",
            "connection",
            "transfer-encoding",
            "content-length",
            "keep-alive",
            "upgrade",
            "te",
            "trailer",
        }
        return {k: v for k, v in headers.items() if k.lower() not in excluded}

    def _generate_cache_key(self, request: Request) -> str:
        """
        Generate a unique cache key from request.
        Includes hashed Authorization header (if present) for per-user caching.
        """

        key_parts = [
            request.method,
            request.url.path,
            str(sorted(request.query_params.items())),
        ]

        # Include hashed authorization header if present (use standard Authorization header)
        auth_header = request.headers.get("Authorization", "")
        if auth_header:
            # Hash the auth header to avoid storing raw tokens in the cache key
            auth_hash = hashlib.sha256(auth_header.encode()).hexdigest()[:16]
            key_parts.append(f"auth:{auth_hash}")

        key_string = "|".join(key_parts)

        cache_key = hashlib.sha256(key_string.encode()).hexdigest()

        return f"cache:{cache_key}"

    def _is_cacheable(self, request: Request) -> bool:
        """
        Determine if a request should be cached.
        """
        # Only cache GET requests
        if request.method != "GET":
            return False

        # Cache only specific GET endpoints
        cacheable_paths = [
            "/health",
            "/health/components",
            "/artifacts",
            "/artifact/",
            "/tracks",
        ]

        # Check if path starts with any cacheable pattern
        path = request.url.path
        is_cacheable = any(path.startswith(pattern) for pattern in cacheable_paths)

        # Explicitly exclude mutation endpoints even if they somehow match
        non_cacheable = ["/reset", "/authenticate"]
        if any(pattern in path for pattern in non_cacheable):
            return False

        return is_cacheable

    async def get(self, request: Request) -> Optional[Response]:
        """
        Retrieve cached response for request.
        Uses thread-wrapped Redis calls to avoid blocking the event loop.
        """
        if not self.is_available():
            return None

        if not self._is_cacheable(request):
            return None

        try:
            cache_key = self._generate_cache_key(request)
            # Run Redis get in a thread to avoid blocking
            cached_data = await asyncio.to_thread(self.redis_client.get, cache_key)

            if cached_data:
                logger.debug(f"Cache HIT for {request.url.path}")
                data = json.loads(cached_data)

                # Decode body: check if it was base64-encoded
                content = data.get("content", "")
                if data.get("is_base64", False):
                    content = base64.b64decode(content.encode()).decode(
                        "utf-8", errors="replace"
                    )

                # Reconstruct response
                return Response(
                    content=content,
                    status_code=data.get("status_code", 200),
                    headers=data.get("headers", {}),
                    media_type=data.get("media_type", "application/json"),
                )
            else:
                logger.debug(f"Cache MISS for {request.url.path}")
                return None

        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")
            return None

    async def set(
        self, request: Request, response: Response, ttl: Optional[int] = None
    ) -> Response:
        if not self.is_available() or not self._is_cacheable(request):
            return response

        if response.status_code >= 400:
            return response

        # Check Cache-Control header to respect no-store and private directives
        cache_control = response.headers.get("cache-control", "").lower()
        if "no-store" in cache_control or "private" in cache_control:
            logger.debug(
                f"Skipping cache for {request.url.path} (Cache-Control: {cache_control})"
            )
            return response

        try:
            cache_key = self._generate_cache_key(request)

            # Collect body bytes safely from various Response types
            body = b""
            # Prefer an async body iterator if present
            body_iterator = getattr(response, "body_iterator", None)
            if body_iterator is not None:
                body_chunks = []
                async for chunk in body_iterator:
                    body_chunks.append(chunk)
                body = b"".join(body_chunks)
            else:
                # Try common attributes
                resp_body = getattr(response, "body", None)
                if resp_body is not None:
                    body = (
                        resp_body
                        if isinstance(resp_body, (bytes, bytearray))
                        else str(resp_body).encode()
                    )
                else:
                    resp_content = getattr(response, "content", None)
                    if resp_content is not None:
                        body = (
                            resp_content
                            if isinstance(resp_content, (bytes, bytearray))
                            else str(resp_content).encode()
                        )
                    else:
                        # Last-resort attempts: try internal iterator names if any (best-effort)
                        potential = response.__dict__.get(
                            "_body_iterator"
                        ) or response.__dict__.get("background")
                        if potential:
                            try:
                                body_chunks = []
                                async for chunk in potential:
                                    body_chunks.append(chunk)
                                body = b"".join(body_chunks)
                            except Exception:
                                body = b""
                        else:
                            body = b""

            # Base64-encode body for safe storage (handles binary and text)
            is_base64 = False
            try:
                # Try to decode as UTF-8; if it fails, store as base64
                body_str = body.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                body_str = base64.b64encode(body).decode("utf-8")
                is_base64 = True

            # Strip sensitive headers before caching
            safe_headers = self._filter_headers_for_caching(dict(response.headers))

            cache_data = {
                "content": body_str,
                "is_base64": is_base64,
                "status_code": response.status_code,
                "headers": safe_headers,
                "media_type": response.media_type,
            }

            ttl_seconds = ttl if ttl is not None else self.default_ttl
            # Run Redis setex in a thread to avoid blocking
            await asyncio.to_thread(
                self.redis_client.setex, cache_key, ttl_seconds, json.dumps(cache_data)
            )

            logger.debug(
                f"Cached response for {request.url.path} (TTL: {ttl_seconds}s)"
            )

            # Return NEW response with reconstructed body
            from fastapi import Response as FastAPIResponse

            return FastAPIResponse(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        except Exception as e:
            logger.warning(f"Cache storage error: {e}")
            # Return original response if caching fails
            return response

    def invalidate_on_mutation(self, pattern: str = "*") -> int:
        if not self.is_available():
            return 0

        try:
            # Use scan_iter to avoid blocking on large keyspaces
            keys = list(self.redis_client.scan_iter(f"cache:{pattern}"))
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries (pattern: {pattern})")
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
            return 0

    def get_stats_internal(self) -> Dict[str, Any]:
        """
        Get cache statistics for internal monitoring/health checks.

        Returns:
            Dictionary with cache stats
        """
        if not self.is_available():
            return {"status": "unavailable"}

        try:
            info = self.redis_client.info("stats")
            keys = list(self.redis_client.scan_iter("cache:*"))

            return {
                "status": "available",
                "total_keys": len(keys),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0), info.get("keyspace_misses", 0)
                ),
            }
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _calculate_hit_rate(hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage"""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


# Global config for backend server

# Initialize Redis cache
CACHE_CONFIG = {
    "password": os.getenv("REDIS_PASSWORD", ""),
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "db": int(os.getenv("REDIS_DB", "0")),
    "default_ttl": int(os.getenv("CACHE_TTL", "3600")),
}

# Global cache instance
cache_router = CacheRouter(**CACHE_CONFIG)


def generate_400_error_return():
    """Generate 400 error response"""
    return JSONResponse(
        status_code=400,
        content={"error": "Bad Request", "message": "Invalid request format"},
    )


api_core = FastAPI()

is_devel = getenv("DEVEL_TEST")
if is_devel is None:
    is_devel = "true"
if is_devel.lower() == "true":
    api_core.mount(
        "/static",
        StaticFiles(directory="src/frontend_server/view/static"),
        name="static",
    )


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware that implements transparent caching for GET requests.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            # Handle /reset endpoint
            if request.url.path == "/reset" and request.method == "DELETE":
                logger.info("Reset endpoint called - invalidating all cache")
                cache_router.invalidate_on_mutation("*")
                response = await self._handle_request(request, call_next)
                return response

            # Check cache for GET requests
            if request.method == "GET":
                cached_response = await cache_router.get(request)

                if cached_response is not None:
                    logger.debug(f"Cache hit for {request.url.path}")
                    return cached_response

                logger.debug(f"Cache miss for {request.url.path}")

            # Process request and cache if appropriate
            response = await self._handle_request(request, call_next)

            # Cache successful GET responses
            if (
                request.method == "GET"
                and cache_router.is_available()
                and response.status_code < 400
            ):
                cached_response = await cache_router.set(request, response)
                if cached_response:
                    return cached_response

            # Invalidate cache on mutation operations
            if (
                request.method in ["POST", "PUT", "DELETE"]
                and response.status_code < 400
            ):
                # Extract artifact type/id from path for targeted invalidation
                path_parts = request.url.path.split("/")
                if "artifact" in path_parts:
                    # Invalidate artifact-related cache
                    cache_router.invalidate_on_mutation("*artifact*")
                    logger.debug("Invalidated artifact cache after mutation")

            return response

        except Exception as e:
            logger.error(f"Cache middleware error: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": "Internal Server Error", "message": str(e)},
            )

    async def _handle_request(self, request: Request, call_next) -> Response:
        """
        Handle request by routing to internal router or backend.
        """
        # Check if endpoint exists in internal router
        if self._endpoint_exists_in_api_core(request):
            return await call_next(request)
        else:
            # Forward to backend server
            return await self._forward_to_backend(request)

    async def _forward_to_backend(self, request: Request) -> Response:
        """Forward request to backend server"""
        try:
            async with httpx.AsyncClient(timeout=BACKEND_CONFIG["timeout"]) as client:
                # Prepare the request
                url = f"{BACKEND_CONFIG['base_url']}{request.url.path}"
                if request.url.query:
                    url += f"?{request.url.query}"

                # Get request body
                body = await request.body()

                # Forward the request
                logger.debug(f"Forwarding request to backend: {url}")
                backend_response = await client.request(
                    method=request.method,
                    url=url,
                    headers=dict(request.headers),
                    content=body,
                )

                # Create response
                return Response(
                    content=backend_response.content,
                    status_code=backend_response.status_code,
                    headers=dict(backend_response.headers),
                )

        except httpx.TimeoutException:
            logger.error("Backend request timeout")
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Gateway Timeout",
                    "message": "Backend server timeout",
                },
            )
        except Exception as e:
            logger.error(f"Backend forwarding error: {e}")
            return JSONResponse(
                status_code=502, content={"error": "Backend Error", "message": str(e)}
            )

    def _endpoint_exists_in_api_core(self, request: Request) -> bool:
        """Check if the endpoint exists in the api_core router using route matching.

        Uses Starlette's route matching to properly handle path parameters (e.g., /artifact/{id}).
        """
        try:
            from starlette.routing import Match
            from fastapi.routing import APIRoute

            # Build request scope for route matching
            scope = {
                "type": "http",
                "method": request.method,
                "path": request.url.path,
                "headers": request.headers.raw,
                "query_string": (
                    request.url.query.encode() if request.url.query else b""
                ),
            }

            # Check api_core routes using proper route matching
            for route in api_core.routes:
                if isinstance(route, APIRoute):
                    match, child_scope = route.matches(scope)
                    if match == Match.FULL:
                        # Verify method is allowed
                        route_methods = getattr(route, "methods", None)
                        if route_methods and request.method.upper() in route_methods:
                            # Forward json requests to the backend if we only have a webui endpoint
                            try:
                                from fastapi.responses import HTMLResponse

                                route_response_class = getattr(
                                    route, "response_class", None
                                )

                                accept_header = request.headers.get("accept", "")
                                accepts_html = (
                                    (not accept_header)
                                    or "*/*" in accept_header
                                    or "text/html" in accept_header
                                )

                                is_html_route = (
                                    route_response_class is not None
                                    and isinstance(route_response_class, type)
                                    and issubclass(route_response_class, HTMLResponse)
                                )

                                if is_html_route and not accepts_html:
                                    continue
                            except Exception:
                                pass

                            return True
            return False
        except Exception as e:
            logger.debug(f"Error checking endpoint in api_core: {e}")
            return False


@api_core.on_event("startup")
async def startup_event():
    """Log cache status on startup and report to health monitoring"""
    if cache_router.is_available():
        logger.info("Redis cache enabled and connected")
        stats = cache_router.get_stats_internal()
        logger.info(f"  Cache stats: {stats}")

        # Publish cache availability metric to CloudWatch if configured
        try:
            from src.frontend_server.model.cloudwatch_publisher import (
                CloudWatchPublisher,
            )

            cache_metrics = CloudWatchPublisher("cache_layer")
            cache_metrics.publish_metric("CacheAvailable", 1, unit="Count")
        except Exception as e:
            logger.debug(f"CloudWatch metrics not available: {e}")
    else:
        logger.warning("⚠ Redis cache not available - running without cache")

        # Publish cache unavailability metric
        try:
            from src.frontend_server.model.cloudwatch_publisher import (
                CloudWatchPublisher,
            )

            cache_metrics = CloudWatchPublisher("cache_layer")
            cache_metrics.publish_metric("CacheAvailable", 0, unit="Count")
        except Exception:
            pass


@api_core.on_event("shutdown")
async def shutdown_event():
    """Cleanup cache connection on shutdown"""
    if cache_router.is_available() and cache_router.redis_client:
        try:
            # Get final stats before shutdown
            stats = cache_router.get_stats_internal()
            logger.info(f"Final cache stats: {stats}")

            # Close connection
            cache_router.redis_client.close()
            logger.info("Redis cache connection closed")
        except Exception as e:
            logger.warning(f"Error closing cache connection: {e}")


# Add the middleware to api_core
api_core.add_middleware(CacheMiddleware)
api_core.include_router(health_router)
api_core.include_router(webpage_router)


def get_cache_metrics_for_monitoring() -> Dict[str, Any]:
    """
    Internal function for health monitoring components to access cache metrics.

    Returns:
        Cache statistics dictionary
    """
    return cache_router.get_stats_internal()


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Internal function to invalidate cache by pattern.

    Args:
        pattern: Redis key pattern

    Returns:
        Number of keys deleted
    """
    return cache_router.invalidate_on_mutation(pattern)
