# Authentication

Future authentication uses named providers. Providers return one normalized `Identity`; middleware decides which routes require a provider, and scope middleware performs authorization.

## HTTP Basic

Authentication code remains a class in `app/authentication`. An application-specific Basic implementation can reuse the packaged parser while keeping credential lookup in its authentication class:

```python
from future.authentication.BasicAuthentication import BasicAuthentication
from future.authentication.Identity import Identity

class DatabaseAuthentication(BasicAuthentication):
    def __init__(self) -> None:
        super().__init__(verify_credentials=self._verify_credentials)

    async def _verify_credentials(self, username: str, password: str) -> Identity | None:
        user = await User.where("username", username).first()
        if user is None or not verify_password(password, user.password_hash):
            return None
        return Identity(subject=str(user.id), provider="basic", scopes=("profile:read",))

config = {
    "AUTHENTICATION": {
        "default": "basic",
        "providers": {
            "basic": {
                "driver": DatabaseAuthentication,
            },
        },
    },
}
```

Custom authentication classes end in `Authentication`, live in `app/authentication`, implement `authenticate(request)`, and return `Identity | None`. The driver constructor is resolved by Future; configured `options` can supply protocol values such as issuers and client IDs to reusable packaged authentication classes.

## Routes

Routes stay inline and each route declaration stays on one line:

```python
routes = [
    RouteGroup(
        name="Account",
        middlewares=[AuthenticationMiddleware, ScopeValidationMiddleware],
        routes=[
            Get("/profile", ProfileController.show, "profile.show", scopes=["profile:read"]),
        ],
    ),
    RouteGroup(
        name="Employees",
        middlewares=[AuthenticationMiddleware(provider="ldap"), ScopeValidationMiddleware],
        routes=[
            Get("/employees", EmployeeController.index, "employees.index", scopes=["employees:read"]),
        ],
    ),
]
```

`AuthenticationMiddleware` returns 401 when credentials are missing or invalid. `ScopeValidationMiddleware` requires every scope declared on the matched route and returns 403 when an authenticated identity lacks one. Controllers read `self.request.identity`; the request never exposes the application container.
