from fastapi import Depends, APIRouter, status, Response
from src.frontend_controller.authentication.auth_object import AccessLevel, access_level, VerifyAuth


reset_router = APIRouter()
async def reset_registry():
    pass


@reset_router.delete("/reset", status_code = status.HTTP_200_OK)
async def reset(response: Response):
    response.body = "Registry is reset."