from future.authentication.Identity import Identity


async def verify_credentials(username: str, password: str) -> Identity | None:
    if password != "secret" or username not in {"reader", "admin"}:
        return None
    scopes = ("users:read", "users:admin") if username == "admin" else ("users:read",)
    return Identity(subject=username, provider="basic", roles=(username,), scopes=scopes)
