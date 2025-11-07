from fastapi import APIRouter, status, Response


reset_router = APIRouter()
async def reset_registry():
    pass


@reset_router.delete("/reset", status_code = status.HTTP_200_OK)
async def reset(response: Response):
    response.body = "Registry is reset."