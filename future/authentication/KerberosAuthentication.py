"""
Kerberos Single Sign-On authentication.
"""

from future.interfaces.IAuthentication import IAuthentication
from future.authentication.Identity import Identity
from future.request import Request


class KerberosAuthentication(IAuthentication):
    auth_type = "sso"

    async def authenticate(self, request: Request) -> Identity | None:
        message = "Kerberos authentication is not implemented yet"
        raise NotImplementedError(message)
