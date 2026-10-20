# Dependencies and the application container

Future owns a small application container. Applications do not build it, pass it around, or resolve objects from it. Add annotated constructor dependencies and Future constructs the object graph when it handles a request.

```python
app = Future(config=config)
app.add_routes(routes)
app.run()
```

There is no `build_container()`, application provider, dependency decorator, or container property on `Request`.

## How resolution works

When a route matches, Future:

1. Creates the request and response objects.
2. Resolves middleware classes and the route's controller.
3. Reads each constructor's type annotations.
4. Recursively constructs concrete dependencies.
5. Supplies the request and response where those types are requested.
6. Runs the middleware and controller action.

For example, resolving `UserController` below produces `UserController -> UserService -> UserRepository` automatically:

```python
from future.interfaces.IController import IController
from future.request import Request
from future.response import Response

class UserRepository:
    async def find(self, user_id: str):
        return await User.find(user_id)

class UserService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

class UserController(IController):
    def __init__(self, request: Request, response: Response, users: UserService) -> None:
        super().__init__(request, response)
        self.users = users
```

There is no dependency list in config. `Request` and `Response` are supplied by Future; `UserService` and `UserRepository` are constructed from their annotations.

Concrete classes do not need registration. Required constructor parameters must have type annotations. Primitive configuration such as URLs, secrets, client IDs, and timeouts belongs in application settings or in the explicit options of framework components such as authentication providers.

## Lifetimes

| Object | Lifetime |
|--------|----------|
| `Request` and `Response` | One matched request |
| Controller | A new instance for each request |
| Concrete controller dependencies | Constructed with that controller's dependency graph |
| Middleware class | Resolved and bound for each request |
| Configured middleware instance | Treated as an immutable definition and copied before request binding |
| Framework component | One application instance, started and stopped with ASGI lifespan |
| Test override | The explicit value supplied by the test |

Framework components are shared services owned by Future. The database registry and authentication provider registry are current examples. Future starts components in registration order and stops them in reverse order. If startup fails partway through, already-started components are stopped before the error is propagated.

## Interchangeable implementations

Only ambiguous interfaces need a binding. Define an application contract with `Interface`, implement it, and select the implementation in `BINDINGS`:

```python
from future.interfacing import Interface

class IUserRepository(Interface):
    async def find(self, user_id: str) -> dict | None:
        raise NotImplementedError

class DatabaseUserRepository(IUserRepository):
    async def find(self, user_id: str) -> dict | None:
        user = await User.find(user_id)
        return user.to_dict() if user else None

class LdapUserRepository(IUserRepository):
    async def find(self, user_id: str) -> dict | None:
        return await ldap_client.find_user(user_id)

config = {
    "BINDINGS": {
        IUserRepository: LdapUserRepository,
    },
}
```

Services depend on the contract rather than choosing a data source:

```python
class UserService:
    def __init__(self, users: IUserRepository) -> None:
        self.users = users

    async def find(self, user_id: str) -> dict | None:
        return await self.users.find(user_id)

class UserController(IController):
    def __init__(self, request: Request, response: Response, users: UserService) -> None:
        super().__init__(request, response)
        self.users = users

    async def show(self, user_id: str) -> Response:
        user = await self.users.find(user_id)
        return self.response.json(user)

routes = [
    Get("/users/<str:user_id>", UserController.show, "users.show"),
]
```

To switch the whole application to the database implementation, only the ambiguous choice changes:

```python
"BINDINGS": {
    IUserRepository: DatabaseUserRepository,
}
```

This is useful when an application can load users from a database, LDAP, or a coordinating hybrid repository. `UserService` itself remains unregistered because it is a concrete class. Changing SQLite to PostgreSQL does not require a repository binding because Future Models already abstract supported database drivers.

## Middleware dependencies

Middleware classes use the same constructor resolution. Request and response binding still happens internally:

```python
class AuditMiddleware(IMiddleware):
    def __init__(self, audit: AuditService) -> None:
        super().__init__()
        self.audit = audit

    async def before(self) -> Response | None:
        await self.audit.record(self.request)
        return None

routes = [
    Get("/reports", ReportController.index, "reports.index", middlewares=[AuditMiddleware]),
]
```

When middleware needs an explicit route-level option, pass a configured instance instead. Future copies that definition for every request, so request state is never written back to the route definition:

```python
middlewares=[AuthenticationMiddleware(provider="ldap")]
```

See [Middleware](middleware.md) and [Authentication](authentication.md) for complete route examples.

## Test overrides

Tests can replace a contract or concrete dependency on the application:

```python
fake_users = FakeUserRepository()
app.override(IUserRepository, fake_users)
```

The supplied value is used whenever the dependency is requested. Production configuration remains unchanged, and tests do not need direct access to the container.

## Resolution errors

Resolution is limited to constructors. Future does not inject controller action arguments, scan directories, use decorators, or expose the container on `Request`. Missing annotations, missing interface bindings, and dependency cycles raise errors with the dependency chain.

Unknown explicit component options also fail during construction instead of being silently ignored. This catches misspelled authentication options and similar configuration mistakes early.
