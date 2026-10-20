# Middleware
`future.interfaces.IMiddleware` runs around controller actions. Same `request` / `response` injection as controllers.

```python
from typing import Optional
from future.interfaces.IMiddleware import IMiddleware
from future.response import Response
from future.exceptions import HTTPException

class ApiKeyMiddleware(IMiddleware):
    async def before(self) -> Optional[Response]:
        if not self.request.headers.get("x-api-key"):
            raise HTTPException("unauthorized", 401)
        return None

    async def after(self) -> Optional[Response]:
        return None
```

## Applying middleware

Pass middleware classes directly to `middlewares`. Put shared middleware on a `RouteGroup`, or put middleware on one route when it only applies there:

```python
from future.middleware.CORSMiddleware import CORSMiddleware
from future.routing import Get, RouteGroup
from app.controllers.HealthController import HealthController
from app.controllers.StockController import StockController

routes = [
    Get("/health", HealthController.show, "health", middlewares=[CORSMiddleware]),
    RouteGroup(
        prefix="/stocks",
        name="Stocks",
        middlewares=[ApiKeyMiddleware],
        routes=[
            Get("/", StockController.index, "stocks.index"),
            Get("/<str:stock_id>", StockController.show, "stocks.show"),
        ],
    ),
]
```

Middleware constructors are application configuration, so configured instances can be used directly:

```python
from future.middleware.AuthenticationMiddleware import AuthenticationMiddleware

middlewares=[AuthenticationMiddleware(provider="ldap")]
```

Future keeps the route-level definition immutable and binds a request-local copy. Class-only middleware remains supported and uses its defaults.

- `before` runs outer → inner → controller
- `after` runs in reverse
- Return a `Response` from `before` to short-circuit (skip the controller)

## Built-ins
Import from the class file: CORS, GZip, CSRF, RateLimit, Session, ScopeValidation. Confuser classes exist but are unfinished — see [Gaps](gaps.md).

## Scopes

`AuthenticationMiddleware` uses a named provider and stores its normalized `Identity` on `request.identity`. `ScopeValidationMiddleware` compares the scopes declared by the route with `request.identity.scopes`.

```python
from future.middleware.AuthenticationMiddleware import AuthenticationMiddleware
from future.middleware.ScopeValidationMiddleware import ScopeValidationMiddleware
from future.routing import Get, Post, RouteGroup
from app.controllers.EmployeeController import EmployeeController

routes = [
    RouteGroup(
        prefix="/employees",
        name="Employees",
        middlewares=[AuthenticationMiddleware(provider="ldap"), ScopeValidationMiddleware],
        routes=[
            Get("/", EmployeeController.index, "employees.index", scopes=["employees:read"]),
            Get("/<str:employee_id>", EmployeeController.show, "employees.show", scopes=["employees:read"]),
            Post("/", EmployeeController.create, "employees.create", scopes=["employees:read", "employees:write"]),
        ],
    ),
]
```

Every declared scope is required. In this example, listing or viewing employees requires `employees:read`; creating one requires both `employees:read` and `employees:write`.

- Missing or invalid credentials return 401.
- An authenticated identity missing any required scope returns 403.
- A route without `scopes=` is skipped by `ScopeValidationMiddleware`. It is still authenticated when `AuthenticationMiddleware` applies to its route or group.

Authentication runs before scope validation based on middleware priority, so the order shown above remains readable but is not responsible for security. See [Authentication](authentication.md) for provider configuration and creating an `Identity` with scopes.

## Sessions
```python
from future.middleware.SessionMiddleware import SessionMiddleware
from future.routing import RouteGroup, Get, Post

RouteGroup(
    name="Auth",
    middlewares=[SessionMiddleware],
    routes=[
        Post("/login", AuthController.login, "login"),
        Get("/me", AuthController.me, "me"),
    ],
)
```

Then `self.request.session["user"] = "alice"`.
