from fastapi import FastAPI, Depends
from src.controller import accessor_api, cost_api, exceptions, lineage_api, rater_api, reset_api
from src.controller.authentication.auth_object import VerifyAuth


api_core = FastAPI(dependencies=[Depends(VerifyAuth())])
exceptions.register_exception_handlers(api_core)

api_core.include_router(accessor_api.accessor_router)
api_core.include_router(cost_api.cost_router)
api_core.include_router(rater_api.rater_router)
api_core.include_router(reset_api.reset_router)
api_core.include_router(lineage_api.lineage_router)