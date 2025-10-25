from enum import Enum
from pydantic import validate_call
from fastapi import Request, Response, HTTPException
from ..api_types import *


ENFORCING_AUTHENTICATION: bool = False

class AccessLevel(Enum):
    NO_AUTHENTICATION = 0,
    USER_AUTHENTICATION = 1,
    ADMIN_AUTHENTICATION = 2


def access_level(level: AccessLevel):
    def decorator(func):
        setattr(func, "access_level", level)
        return func
    return decorator


class AuthenticatorReturn(Enum):
    OK = 0,
    BAD_TOKEN = 1,
    BAD_AUTHENTICATION = 2


class Authenticator:
    @validate_call
    def __init__(self, request: Request):
        self.level: AccessLevel = getattr(request.scope["route"].endpoint, "access_level", "public")

    @validate_call
    def check_authentication(self, x_authorization: str) -> AccessLevel:
        return AccessLevel.NO_AUTHENTICATION

    @validate_call
    async def authenticate(self, x_authorization: str | None) -> AuthenticatorReturn:
        if not ENFORCING_AUTHENTICATION:
            return AuthenticatorReturn.OK
        elif not x_authorization:
            return AuthenticatorReturn.BAD_TOKEN
        elif self.check_authentication(x_authorization).value < self.level.value:
            return AuthenticatorReturn.BAD_AUTHENTICATION
        return AuthenticatorReturn.BAD_TOKEN

    @validate_call
    async def authenticate_to_artifact(self, id: ArtifactID, x_authorization: str | None) -> AuthenticatorReturn:
        return AuthenticatorReturn.OK


class AuthClass(Enum):
    AUTH_STANDARD = 0,
    AUTH_ARTIFACT = 1
class VerifyAuth:
    def __init__(self, bad_permissions_message: str = "Not Authorized for Operation", auth_class: AuthClass = AuthClass.AUTH_STANDARD):
        self.bad_permissions_message: str = bad_permissions_message
        self.auth_class: AuthClass = auth_class

    async def special_auth(self, x_authorization: str | None, request: Request, authenticator: Authenticator) -> AuthenticatorReturn:
        match self.auth_class:
            case AuthClass.AUTH_STANDARD:
                return AuthenticatorReturn.OK
            case AuthClass.AUTH_ARTIFACT:
                return await authenticator.authenticate_to_artifact(x_authorization, request.path_params["id"])

    async def __call__(self, request: Request, x_authorization: str | None = Header(None, alias="X-Authorization")):
        authenticator: Authenticator = Authenticator(request)
        match await authenticator.authenticate(x_authorization):
            case AuthenticatorReturn.OK:
                return self.special_auth(x_authorization, request, authenticator)
            case AuthenticatorReturn.BAD_TOKEN:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=self.bad_permissions_message)
            case AuthenticatorReturn.BAD_AUTHENTICATION:
                raise HTTPException(status_code=403, detail="Authentication failed due to invalid or missing AuthenticationToken.")