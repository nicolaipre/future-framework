from future.interfacing import Interface


class IUserRepository(Interface):
    async def find(self, user_id: str) -> dict[str, str] | None:
        raise NotImplementedError
