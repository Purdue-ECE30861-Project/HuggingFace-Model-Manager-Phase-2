@access_level(AccessLevel.NO_AUTHENTICATION)
@app.post("/artifacts", status_code = status.HTTP_200_OK)
async def get_artifacts(
        response: Response,
        body: ArtifactQuery,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        offset: str = Query(..., pattern=r"^\d+$"),
        x_authorization: str = Depends(VerifyAuth())
) -> List[ArtifactMetadata] | None:
    return_code: GetArtifactsEnum
    return_content: List[ArtifactMetadata]

    return_code, return_content = accessor.get_artifacts(body, offset)

    match return_code:
        case return_code.SUCCESS:
            response.headers["offset"] = str(int(offset) + 1)
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.TOO_MANY_ARTIFACTS:
            raise HTTPException(status_code=return_code.value, detail="Too many artifacts returned.")


@access_level(AccessLevel.NO_AUTHENTICATION)
@app.post("/artifact/byName/{name}", status_code = status.HTTP_200_OK)
async def get_artifacts_by_name(
        name: ArtifactName,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth())
) -> List[ArtifactMetadata] | None:
    return_code: GetArtifactEnum
    return_content: List[ArtifactMetadata]

    return_code, return_content = accessor.get_artifact_by_name(name)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="No such artifact.")


@access_level(AccessLevel.NO_AUTHENTICATION)
@app.post("/artifact/byRegEx", status_code = status.HTTP_200_OK)
async def get_artifacts_by_name(
        regex: ArtifactRegEx,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth())
) -> List[ArtifactMetadata] | None:
    return_code: GetArtifactEnum
    return_content: List[ArtifactMetadata]

    return_code, return_content = accessor.get_artifact_by_regex(regex)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="No artifact found under this regex.")


@access_level(AccessLevel.NO_AUTHENTICATION)
@app.get("/artifacts/{artifact_type}/{id}")
async def get_artifact(
        artifact_type: ArtifactType,
        id: ArtifactID,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth())
) -> Artifact | None:
    return_code: GetArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.get_artifact(artifact_type, id)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@access_level(AccessLevel.USER_AUTHENTICATION)
@app.put("/artifacts/{artifact_type}/{id}", status_code=status.HTTP_200_OK)
async def update_artifact(
        artifact_type: ArtifactType,
        id: ArtifactID,
        body: Artifact,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth(auth_class=AuthClass.AUTH_ARTIFACT))
) -> None:
    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.update_artifact(artifact_type, id, body)

    match return_code:
        case return_code.SUCCESS:
            response.content = "version is updated."
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@access_level(AccessLevel.USER_AUTHENTICATION)
@app.delete("/artifacts/{artifact_type}/{id}", status_code=status.HTTP_200_OK)
async def delete_artifact(
        artifact_type: ArtifactType,
        id: ArtifactID,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth(auth_class=AuthClass.AUTH_ARTIFACT))
) -> None:
    return_code: GetArtifactEnum
    return_content: None

    return_code, return_content = accessor.delete_artifact(artifact_type, id)

    match return_code:
        case return_code.SUCCESS:
            response.content = "Artifact is deleted."
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.DOES_NOT_EXIST:
            raise HTTPException(status_code=return_code.value, detail="Artifact does not exist.")


@access_level(AccessLevel.USER_AUTHENTICATION)
@app.post("/artifacts/{artifact_type}", status_code=status.HTTP_201_CREATED)
async def register_artifact(
        artifact_type: ArtifactType,
        body: ArtifactData,
        response: Response,
        accessor: Annotated[ArtifactAccessor, Depends(artifact_accessor)],
        x_authorization: str = Depends(VerifyAuth())
) -> Artifact | None:
    return_code: RegisterArtifactEnum
    return_content: Artifact

    return_code, return_content = accessor.register_artifact(artifact_type, body)

    match return_code:
        case return_code.SUCCESS:
            return return_content
        case return_code.INVALID_REQUEST:
            raise RequestValidationError(errors=["internal"])
        case return_code.ALREADY_EXISTS:
            raise HTTPException(status_code=return_code.value,
                                detail="Authentication failed due to invalid or missing AuthenticationToken.")
        case return_code.DISQUALIFIED:
            raise HTTPException(status_code=return_code.value,
                                detail="Artifact is not registered due to the disqualified rating.")