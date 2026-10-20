from future.interfaces.IController import IController
from future.response import Response


class HealthController(IController):
    async def show(self) -> Response:
        return self.response.json({"status": "ok"})
