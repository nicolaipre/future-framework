from future.interfaces.IMiddleware import IMiddleware
from future.response import Response

from examples.container_app.app.services.AuditService import AuditService


class AuditMiddleware(IMiddleware):
    priority = 5

    def __init__(self, audit: AuditService) -> None:
        super().__init__()
        self.audit = audit

    async def before(self) -> Response | None:
        self.request.context["audit"] = self.audit.describe(self.request.method, self.request.path)
        return None
