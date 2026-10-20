"""
Azure AD authentication.
"""

from future.interfaces.IAuthentication import IAuthentication
from future.authentication.Identity import Identity
from future.request import Request


class AzureADAuthentication(IAuthentication):
    auth_type = "basic"

    async def authenticate(self, request: Request) -> Identity | None:
        message = "Azure AD authentication is not implemented yet"
        raise NotImplementedError(message)
