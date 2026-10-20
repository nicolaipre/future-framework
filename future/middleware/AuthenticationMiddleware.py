from typing import Optional

from future.authentication.AuthenticationComponent import AuthenticationComponent
from future.interfaces.IMiddleware import IMiddleware
from future.response import Response


class AuthenticationMiddleware(IMiddleware):
    name = "AuthenticationMiddleware"
    priority = 0

    def __init__(self, provider: str | None = None) -> None:
        super().__init__()
        self.provider = provider

    async def before(self) -> Optional[Response]:
        authentication = self._resolve_dependency(AuthenticationComponent)
        identity = await authentication.authenticate(self.request, self.provider)
        if identity is None:
            challenge = getattr(authentication.get(self.provider), "challenge", None)
            headers = {"www-authenticate": str(challenge)} if challenge else None
            return self.response.json({"error": "Unauthenticated", "status_code": 401}, status=401, headers=headers)
        self.request.identity = identity
        self.request.context["identity"] = identity
        self.request.context["user_id"] = identity.subject
        self.request.context["scopes"] = list(identity.scopes)
        return None
