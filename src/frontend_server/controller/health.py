from fastapi import APIRouter, Depends
from typing import Annotated
from src.contracts.health_contracts import HealthComponentCollection
from ..model.health_accessor import HealthAccessor


health_router = APIRouter()


@health_router.get("/health", status_code=200)
async def get_health():
    pass


@health_router.get("/health/components", status_code=200)
async def get_component_health(windowMinutes: int, includeTimeline: bool, health_accessor_instance: Annotated[HealthAccessor, Depends(HealthAccessor)]) -> HealthComponentCollection:
    return health_accessor_instance.component_health(windowMinutes, includeTimeline)


@health_router.get("/tracks", status_code=200)
async def get_track():
    return {
        "plannedTracks":[
            "Performance track"
        ]
    }

# we need an endpoint to get logs based on specific component