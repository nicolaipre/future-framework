"""
SAML Single Sign-On authentication.
"""

from future.interfaces.IAuthentication import IAuthentication
from future.authentication.Identity import Identity
from future.request import Request


class SAMLAuthentication(IAuthentication):
    auth_type = "sso"

    async def authenticate(self, request: Request) -> Identity | None:
        message = "SAML authentication is not implemented yet"
        raise NotImplementedError(message)
