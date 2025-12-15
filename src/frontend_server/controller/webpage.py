from fastapi import Request, Form, APIRouter, Query, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from src.frontend_server import BACKEND_CONFIG
import httpx
from typing import Optional, Any, Annotated, Annotated, Union

webpage_router = APIRouter()

templates = Jinja2Templates(directory="src/frontend_server/view/templates")

# Configuration for accessing the middleware
FRONTEND_BASE_URL = "http://localhost:80"
BACKEND_TIMEOUT: int = int(BACKEND_CONFIG.get("timeout", 30.0))


async def fetch_through_middleware(
    endpoint: str,
    method: str = "GET",
    data: Optional[Union[dict[str, Any], list[Any]]] = None,
    params: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """
    Fetch data through the frontend server's middleware.
    This allows the caching middleware to intercept requests.
    """
    try:
        async with httpx.AsyncClient(timeout=BACKEND_TIMEOUT) as client:
            url = f"{FRONTEND_BASE_URL}{endpoint}"

            if method == "GET":
                response = await client.get(
                    url,
                    params=params,
                    headers={
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                )
            elif method == "POST":
                response = await client.post(
                    url,
                    json=data,
                    params=params,
                    headers={
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                )
            elif method == "PUT":
                response = await client.put(
                    url,
                    json=data,
                    headers={
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                )
            elif method == "DELETE":
                response = await client.delete(
                    url,
                    headers={
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                )
                if response.status_code >= 200 and response.status_code < 300:
                    return {"response": response.status_code}
                else:
                    return None
            else:
                return None

            if response.status_code >= 200 and response.status_code < 300:
                return response.json()
            return None
    except Exception:
        return None


@webpage_router.get("/", response_class=HTMLResponse)
async def index(request: Request, offset: int = Query(0)):
    return await artifact_view_page(request=request, offset=offset, message=None)


@webpage_router.post("/search", response_class=HTMLResponse)
async def search(request: Request, regex: Annotated[str, Form()]):
    """Search artifacts using regex"""
    try:
        # Search via middleware using /artifact/byRegEx
        artifacts_data = (
            await fetch_through_middleware(
                "/artifact/byRegEx", method="POST", data={"regex": regex}
            )
            or []
        )

        # Fetch ratings for each artifact if it's a model
        for artifact in artifacts_data:
            if artifact.get("metadata", {}).get("type") == "model":
                artifact_id = artifact.get("metadata", {}).get("id")
                rating = await fetch_through_middleware(
                    f"/artifact/model/{artifact_id}/rate"
                )
                artifact["rating"] = rating
            else:
                artifact["rating"] = None

        context = {
            "request": request,
            "artifacts": artifacts_data,
            "offset": 0,
            "next_offset": 0,
            "has_more": False,
            "search_query": regex,
        }

        return templates.TemplateResponse(
            request=request, name="index.html", context=context
        )
    except Exception as e:
        context = {
            "request": request,
            "artifacts": [],
            "offset": 0,
            "next_offset": 0,
            "has_more": False,
            "error": str(e),
        }
        return templates.TemplateResponse(
            request=request, name="index.html", context=context
        )


@webpage_router.get(
    "/artifact/{artifact_type}/{artifact_id}", response_class=HTMLResponse
)
async def artifact_detail(request: Request, artifact_type: str, artifact_id: str):
    """Detailed artifact information page"""
    try:
        # Fetch artifact details through middleware
        artifact = await fetch_through_middleware(
            f"/artifacts/{artifact_type}/{artifact_id}"
        )
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")

        # Fetch rating if it's a model
        rating = None
        if artifact_type == "model":
            rating = await fetch_through_middleware(
                f"/artifact/model/{artifact_id}/rate"
            )

        # Fetch lineage if it's a model
        lineage = None
        if artifact_type == "model":
            lineage = await fetch_through_middleware(
                f"/artifact/model/{artifact_id}/lineage"
            )

        # Fetch cost information
        cost = await fetch_through_middleware(
            f"/artifact/{artifact_type}/{artifact_id}/cost",
            params={"dependency": "false"},
        )

        context = {
            "request": request,
            "artifact": artifact,
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "rating": rating,
            "lineage": lineage,
            "cost": cost,
        }

        return templates.TemplateResponse(
            request=request, name="artifact_detail.html", context=context
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@webpage_router.post(
    "/artifact/{artifact_type}/{artifact_id}/update", response_class=HTMLResponse
)
async def update_artifact(request: Request, artifact_type: str, artifact_id: str):
    """Update artifact information"""
    try:
        form_data = await request.form()

        update_data = {
            "metadata": {"name": form_data.get("name"), "type": artifact_type},
            "data": {"url": form_data.get("url")},
        }

        # Update through middleware
        result = await fetch_through_middleware(
            f"/artifacts/{artifact_type}/{artifact_id}", method="PUT", data=update_data
        )

        if result:
            # Redirect to artifact detail page
            return templates.TemplateResponse(
                request=request,
                name="artifact_detail.html",
                context={
                    "request": request,
                    "artifact": {
                        "metadata": update_data["metadata"],
                        "data": update_data["data"],
                    },
                    "artifact_type": artifact_type,
                    "artifact_id": artifact_id,
                    "success": "Artifact updated successfully",
                },
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to update artifact")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@webpage_router.delete(
    "/artifact/{artifact_type}/{artifact_id}", response_class=HTMLResponse
)
async def delete_artifact(request: Request, artifact_type: str, artifact_id: str):
    """Delete an artifact"""
    try:
        # Delete through middleware
        result = await fetch_through_middleware(
            f"/artifacts/{artifact_type}/{artifact_id}", method="DELETE"
        )

        if result is not None:
            return await artifact_view_page(
                request=request, offset=0, message="Artifact successfully deleted."
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to delete artifact")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


async def artifact_view_page(
    request: Request, offset: int = Query(0), message: str | None = None
):
    """Main artifacts list page with pagination and search"""
    try:
        # Fetch all artifacts with pagination through middleware
        artifacts_data = (
            await fetch_through_middleware(
                "/artifacts",
                method="POST",
                data=[{"name": "*", "types": ["model", "dataset", "code"]}],
                params={"offset": offset},
            )
            or []
        )
        if not isinstance(artifacts_data, list):
            artifacts_data = []

        next_offset = offset + len(artifacts_data) if artifacts_data else offset

        # Fetch ratings for each artifact if it's a model
        for artifact in artifacts_data:
            artifact_id = artifact.get("id", "N/A")
            rating = await fetch_through_middleware(
                f"/artifact/model/{artifact_id}/rate"
            )
            artifact["rating"] = rating

        context = {
            "request": request,
            "artifacts": artifacts_data,
            "offset": offset,
            "next_offset": next_offset,
            "has_more": len(artifacts_data) > 0,
            "success": message,
        }

        return templates.TemplateResponse(
            request=request, name="index.html", context=context
        )
    except Exception as e:
        context = {
            "request": request,
            "artifacts": [],
            "offset": offset,
            "next_offset": offset,
            "has_more": False,
            "error": str(e),
        }
        return templates.TemplateResponse(
            request=request, name="index.html", context=context
        )


@webpage_router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Artifact upload page"""
    context = {"request": request, "artifact_types": ["model", "dataset", "code"]}
    return templates.TemplateResponse(
        request=request, name="upload.html", context=context
    )


@webpage_router.post("/artifact/create", response_class=HTMLResponse)
async def create_artifact(request: Request):
    """Create a new artifact"""
    try:
        form_data = await request.form()
        artifact_type = form_data.get("artifact_type")
        url = form_data.get("url")

        if not artifact_type or not url:
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Extract filename from URL for default name
        url_str = url if isinstance(url, str) else str(url)

        create_data = {
            "url": url_str,
            "download_url": "",
        }

        # Create through middleware
        result = await fetch_through_middleware(
            f"/artifact/{artifact_type}", method="POST", data=create_data
        )

        if result is not None:
            return await artifact_view_page(
                request=request, offset=0, message="Artifact successfully created"
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to create artifact")
    except Exception as e:
        context = {
            "request": request,
            "artifact_types": ["model", "dataset", "code"],
            "error": str(e),
        }
        return templates.TemplateResponse(
            request=request, name="upload.html", context=context
        )


@webpage_router.post(
    "/artifact/{artifact_type}/{artifact_id}/license-check", response_class=HTMLResponse
)
async def license_check(request: Request, artifact_type: str, artifact_id: str):
    """Check license compatibility"""
    try:
        form_data = await request.form()
        github_url = form_data.get("github_url")

        if not github_url:
            raise HTTPException(status_code=400, detail="GitHub URL is required")

        # Check license through middleware
        license_result = await fetch_through_middleware(
            f"/artifact/{artifact_type}/{artifact_id}/license-check",
            method="POST",
            data={"github_url": github_url},
        )

        # Fetch artifact details through middleware
        artifact = await fetch_through_middleware(
            f"/artifacts/{artifact_type}/{artifact_id}"
        )

        context = {
            "request": request,
            "artifact": artifact or {},
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "license_result": license_result,
            "github_url": github_url,
        }

        return templates.TemplateResponse(
            request=request, name="artifact_detail.html", context=context
        )

        return templates.TemplateResponse(
            request=request, name="artifact_detail.html", context=context
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@webpage_router.get("/health", response_class=HTMLResponse)
async def health_dashboard(request: Request):
    """Health dashboard page"""
    return templates.TemplateResponse(request=request, name="health.html", context={"request": request})
