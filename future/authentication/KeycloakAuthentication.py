"""
Keycloak authentication.
"""

from future.interfaces.IAuthentication import IAuthentication
from future.authentication.Identity import Identity
from future.request import Request


class KeycloakAuthentication(IAuthentication):
    auth_type = "oauth"

    async def authenticate(self, request: Request) -> Identity | None:
        message = "Keycloak authentication is not implemented yet"
        raise NotImplementedError(message)
