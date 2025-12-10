import logging
from fastapi import APIRouter, status, Response

from src.backend_server.global_state import database_manager, s3_accessor, cache_accessor

reset_router = APIRouter()


logger = logging.getLogger(__name__)


@reset_router.delete("/reset", status_code=status.HTTP_200_OK)
async def reset(response: Response):
    database_manager.db_reset()
    s3_accessor.s3_reset()
    cache_accessor.reset()
    logger.info("Full reset complete")
