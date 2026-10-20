from examples.container_app.app.repositories.IUserRepository import IUserRepository


class MemoryUserRepository(IUserRepository):
    users = {
        "1": {"id": "1", "name": "Ada"},
        "2": {"id": "2", "name": "Linus"},
    }

    async def find(self, user_id: str) -> dict[str, str] | None:
        user = self.users.get(user_id)
        return {**user, "source": "memory"} if user else None
