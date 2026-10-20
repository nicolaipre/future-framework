# Authentication

Future authentication uses named providers. Providers return one normalized `Identity`; middleware decides which routes require a provider, and scope middleware performs authorization.

## HTTP Basic

```python
async def verify_credentials(username: str, password: str):
    user = await User.where("username", username).first()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return Identity(subject=str(user.id), provider="basic", scopes=("profile:read",))

config = {
    "AUTHENTICATION": {
        "default": "basic",
        "providers": {
            "basic": {
                "driver": BasicAuthentication,
                "options": {"verify_credentials": verify_credentials},
            },
        },
    },
}
```

Custom providers implement `authenticate(request)` and return `Identity | None`. The driver constructor is resolved by Future; configured `options` supply protocol values such as issuers, client IDs, or verifier callbacks.

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
