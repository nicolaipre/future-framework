"""
OpenID Connect authentication.
"""

from future.interfaces.IAuthentication import IAuthentication
from future.authentication.Identity import Identity
from future.request import Request


class OpenIdConnectAuthentication(IAuthentication):
    auth_type = "oidc"

    async def authenticate(self, request: Request) -> Identity | None:
        message = "OpenID Connect authentication is not implemented yet"
        raise NotImplementedError(message)
