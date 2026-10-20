from __future__ import annotations

import copy

from typing import Any, Optional, TYPE_CHECKING

from future.interfacing import Interface
from future.request import Request
from future.response import Response

if TYPE_CHECKING:
    from future.container import Container


# README - a note on the use of middlewares:
# if a middleware does not RETURN or hit any EXCEPTIONS, it means it passes (all checks ok)
# if it however RETURNS or hits an EXCEPTION, the middleware check will deny further processing of the request.


class IMiddleware(Interface):
    name: Optional[str] = None
    apply: bool = True
    priority: int = 0

    def __init__(self, request: Request | None = None, response: Response | None = None) -> None:
        # Configured route instances are unbound definitions until dispatch.
        # Runtime middleware is always bound before before()/after() is called.
        self.request: Request = request  # type: ignore[assignment]
        self.response: Response = response  # type: ignore[assignment]
        self._container: Container | None = None

    def bind(self, request: Request, response: Response, container: Container) -> "IMiddleware":
        """Create request-local middleware from a configured route definition."""
        middleware = copy.copy(self)
        middleware.request = request
        middleware.response = response
        middleware._container = container
        return middleware

    def _resolve_dependency(self, dependency: Any) -> Any:
        if self._container is None:
            raise RuntimeError("Middleware has not been bound to an application request")
        return self._container.resolve(dependency)

    async def before(self) -> Optional[Response]:
        return None

    async def after(self) -> Optional[Response]:
        return None
