from future.authentication.BasicAuthentication import BasicAuthentication
from future.authentication.Identity import Identity


class TestAuthentication(BasicAuthentication):
    def __init__(self) -> None:
        super().__init__(verify_credentials=self._verify_credentials, realm="Future container example")

    async def _verify_credentials(self, username: str, password: str) -> Identity | None:
        if password != "secret" or username not in {"reader", "admin"}:
            return None
        scopes = ("users:read", "users:admin") if username == "admin" else ("users:read",)
        return Identity(subject=username, provider="basic", roles=(username,), scopes=scopes)
