"""
OAuth 2 authentication.
"""

from future.interfaces.IAuthentication import IAuthentication
from future.authentication.Identity import Identity
from future.request import Request


class OAuth2Authentication(IAuthentication):
    auth_type = "oauth"

    async def authenticate(self, request: Request) -> Identity | None:
        message = "OAuth 2 authentication is not implemented yet"
        raise NotImplementedError(message)
