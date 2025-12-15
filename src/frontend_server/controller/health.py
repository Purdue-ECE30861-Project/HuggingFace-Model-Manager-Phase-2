from fastapi import APIRouter, Depends, Query
from typing import Annotated
from src.contracts.health_contracts import HealthComponentCollection
from ..model.health_accessor import HealthAccessor


health_router = APIRouter()


@health_router.get("/health/components", status_code=200)
async def get_component_health_with_defaults(
    windowMinutes: int = Query(60),
    includeTimeline: bool = Query(False),
    health_accessor_instance: HealthAccessor = Depends(HealthAccessor),
):
    return health_accessor_instance.component_health(windowMinutes, includeTimeline)


@health_router.get("/tracks", status_code=200)
async def get_track():
    return {
        "plannedTracks":[
            "Performance track"
        ]
    }

# we need an endpoint to get logs based on specific component