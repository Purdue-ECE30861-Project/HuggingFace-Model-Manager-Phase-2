from fastapi import APIRouter, HTTPException, status, Header
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from src.contracts.artifact_contracts import (
    SimpleLicenseCheckRequest,
    ArtifactID,
    ArtifactType,
)
from src.backend_server.model.license_checker import LicenseChecker
from src.backend_server.model.artifact_accessor.artifact_accessor import GetArtifactEnum
from src.backend_server import global_state
from src.backend_server.global_state import license_checker as checker

router = APIRouter()


@router.post("/artifact/model/{id}/license-check", status_code=status.HTTP_200_OK)
def artifact_model_license_check(id: str, request: SimpleLicenseCheckRequest):
    """
    Returns a boolean indicating whether the licenses are compatible (true) or not (false).
    """
    # Validate artifact id and type
    try:
        artifact_type_model: ArtifactType = ArtifactType("model")
        id_model: ArtifactID = ArtifactID(id=id)
    except ValidationError:
        raise RequestValidationError(errors=["invalid artifact id"])

    # Fetch artifact using global accessor
    accessor = global_state.artifact_accessor
    return_code, artifact = accessor.get_artifact(artifact_type_model, id_model)

    match return_code:
        case GetArtifactEnum.SUCCESS:
            if not artifact:
                raise HTTPException(
                    status_code=404, detail="Failed to retrieve artifact data."
                )
            model_url = artifact.data.url
        case default:
            raise HTTPException(status_code=502, detail="Failed to retrieve artifact.")

    # Attempt to fetch model license
    try:
        model_license = checker.fetch_model_license(model_url)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to retrieve model license: {e}"
        )

    if model_license is None:
        raise HTTPException(
            status_code=502,
            detail="External license information could not be retrieved.",
        )

    # Attempt to fetch GitHub license
    try:
        code_license = checker.fetch_github_license(request.github_url)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to retrieve code license: {e}"
        )

    if code_license is None:
        raise HTTPException(
            status_code=502,
            detail="External license information could not be retrieved.",
        )

    try:
        result = checker.check_compatibility(model_url, request.github_url)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Upstream license service failed: {e}"
        )

    return result
