async def reset_registry():
    pass

@access_level(AccessLevel.ADMIN_AUTHENTICATION)
@app.delete("/reset", status_code = status.HTTP_200_OK)
async def reset(response: Response, x_authorization: str = Depends(VerifyAuth(bad_permissions_message="You do not have permission to reset the registry."))):
    response.body = "Registry is reset."