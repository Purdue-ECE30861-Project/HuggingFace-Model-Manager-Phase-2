from fastapi import FastAPI, Header, Query, Path, Body, status
from pydantic import BaseModel, Field, field_validator, RootModel

from api_types import *


app = FastAPI()


@app.post("/artifacts")
async def get_artifacts(query: ArtifactQuery, offset: str, )