from examples.container_app.app.repositories.IUserRepository import IUserRepository


class UserService:
    def __init__(self, users: IUserRepository) -> None:
        self.users = users

    async def find(self, user_id: str) -> dict[str, str] | None:
        return await self.users.find(user_id)
