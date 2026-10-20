from future.interfacing import Interface
from future.request import Request

from future.authentication.Identity import Identity


class IAuthentication(Interface):
    auth_type: str = ""

    async def authenticate(self, request: Request) -> Identity | None:
        raise NotImplementedError
