from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .controller import accessor_api, cost_api, lineage_api, rater_api, reset_api
import sys
import logging


logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.INFO)
logging.basicConfig(stream=sys.stdout)
logger.info("Starting Server")
api_core = FastAPI()#dependencies=[Depends(VerifyAuth())])


api_core.include_router(accessor_api.accessor_router)
api_core.include_router(cost_api.cost_router)
api_core.include_router(rater_api.rater_router)
api_core.include_router(reset_api.reset_router)
api_core.include_router(lineage_api.lineage_router)


@api_core.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.errors(), "body": exc.body},
    )

# logging output needs:
# just need log messages in a text file, json format
# correspond to the log schemas in run.py