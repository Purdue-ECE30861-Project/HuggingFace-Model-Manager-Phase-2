from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .controller import accessor_api, cost_api, lineage_api, rater_api, reset_api, audit_api
from src.backend_server.utils.logger import setup_logging
import sys
import logging


setup_logging()
logger = logging.getLogger()
logger.info("Starting Server")
api_core = FastAPI()  # dependencies=[Depends(VerifyAuth())])


api_core.include_router(accessor_api.accessor_router)
api_core.include_router(cost_api.cost_router)
api_core.include_router(rater_api.rater_router)
api_core.include_router(reset_api.reset_router)
api_core.include_router(lineage_api.lineage_router)
api_core.include_router(audit_api.audit_router)


@api_core.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Request Validation Failed\n\tURL: {request.url}\n\tBODY: {request.body}\n\tErrors: {exc.errors()}")
    return JSONResponse(
        status_code=400,
        content={"detail": exc.errors(), "body": exc.body},
    )


@api_core.get("/health", status_code=200)
async def get_health():
    pass


@api_core.get("/tracks", status_code=200)
async def get_track():
    return {
        "plannedTracks":[
            "Performance track"
        ]
    }


# logging output needs:
# just need log messages in a text file, json format
# correspond to the log schemas in run.py
