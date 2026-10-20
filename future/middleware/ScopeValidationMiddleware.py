from typing import Optional

from future.interfaces.IMiddleware import IMiddleware
from future.response import Response


class ScopeValidationMiddleware(IMiddleware):
    name = "scopeValidation"
    priority = 10

    async def before(self) -> Optional[Response]:
        route = getattr(self.request, "route", None)
        if not route:
            return None
        required_scopes = getattr(route, "scopes", [])
        if not required_scopes:
            return None
        identity = self.request.identity
        user_id = identity.subject if identity is not None else self.request.context.get("user_id")
        if not user_id:
            return self.response.json({"error": "Unauthenticated", "status_code": 401}, status=401)
        user_scopes = identity.scopes if identity is not None else self.request.context.get("scopes") or []
        for required_scope in required_scopes:
            if required_scope not in user_scopes:
                return self.response.json({"error": "Insufficient permissions", "status_code": 403}, status=403)
        return None
