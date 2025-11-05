from fastapi import FastAPI
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.requests import Request
from fastapi import FastAPI
from fastapi.responses import JSONResponse


cache_router = FastAPI()


def generate_400_error_return():
    """Generate 400 error response - currently empty as specified"""
    return JSONResponse(
        status_code=400,
        content={"error": "Bad Request", "message": "Invalid request format"}
    )

api_core = FastAPI()

# Global config for backend server
BACKEND_CONFIG = {
    "base_url": "http://localhost:8001",  # Configure as needed
    "timeout": 30.0
}


class CacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Step 1: Check cache router
        try:
            # Create a test request to the cache router
            cache_response = await self._check_cache(request)

            if cache_response.status_code == 200:
                # Cache hit - return immediately
                return cache_response
            elif cache_response.status_code == 400:
                # Bad request format - return error
                return generate_400_error_return()
            elif cache_response.status_code == 404:
                # Cache miss - continue to step 2
                return await self._forward_to_backend(request)
            elif cache_response.status_code == 500:
                # Not cacheable - continue to step 3
                return await self._handle_internal_or_backend(request, call_next)

        except Exception as e:
            # If cache check fails, treat as cache miss
            return await self._forward_to_backend(request)

    async def _check_cache(self, request: Request) -> Response:
        """Check the cache router for a cached response"""
        # This simulates calling the cache router
        # In a real implementation, this would check your cache system

        # For now, returning 404 (cache miss) as default behavior
        # You'll need to implement the actual cache logic here
        return Response(status_code=404)

    async def _forward_to_backend(self, request: Request) -> Response:
        """Forward request to backend server (Step 2)"""
        try:
            async with httpx.AsyncClient(timeout=BACKEND_CONFIG["timeout"]) as client:
                # Prepare the request
                url = f"{BACKEND_CONFIG['base_url']}{request.url.path}"
                if request.url.query:
                    url += f"?{request.url.query}"

                # Get request body
                body = await request.body()

                # Forward the request
                response = await client.request(
                    method=request.method,
                    url=url,
                    headers=dict(request.headers),
                    content=body
                )

                # Return the backend response
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )

        except Exception as e:
            return JSONResponse(
                status_code=502,
                content={"error": "Backend Error", "message": str(e)}
            )

    async def _handle_internal_or_backend(self, request: Request, call_next) -> Response:
        """Handle internal router or forward to backend (Step 3)"""
        try:
            # Check if endpoint exists in internal router (api_core)
            if self._endpoint_exists_in_api_core(request):
                # Execute internal router
                return await call_next(request)
            else:
                # Forward to backend server
                return await self._forward_to_backend(request)

        except Exception as e:
            return await self._forward_to_backend(request)

    def _endpoint_exists_in_api_core(self, request: Request) -> bool:
        """Check if the endpoint exists in the api_core router"""
        # Get the path and method
        path = request.url.path
        method = request.method.lower()

        # Check api_core routes
        for route in api_core.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                if route.path == path and method.upper() in route.methods:
                    return True
        return False


# Add the middleware to api_core
api_core.add_middleware(CacheMiddleware)


