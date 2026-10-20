from future.interfaces.IController import IController
from future.request import Request
from future.response import Response

from examples.container_app.app.services.UserService import UserService


class UserController(IController):
    def __init__(self, request: Request, response: Response, users: UserService) -> None:
        super().__init__(request, response)
        self.users = users

    async def show(self, user_id: str) -> Response:
        identity = self.request.identity
        if identity is None:
            return self.response.json({"error": "Unauthenticated"}, status=401)
        user = await self.users.find(user_id)
        if user is None:
            return self.response.json({"error": "User not found"}, status=404)
        return self.response.json({"user": user, "identity": identity.subject, "audit": self.request.context["audit"]})

    async def admin(self, user_id: str) -> Response:
        identity = self.request.identity
        if identity is None:
            return self.response.json({"error": "Unauthenticated"}, status=401)
        user = await self.users.find(user_id)
        if user is None:
            return self.response.json({"error": "User not found"}, status=404)
        return self.response.json({"user": user, "identity": identity.subject, "admin": True})
