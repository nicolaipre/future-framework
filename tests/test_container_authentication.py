import base64

import pytest

from future.application import Future
from future.authentication import BasicAuthentication, Identity
from future.container import Container, ResolutionError
from future.interfacing import Interface
from future.interfaces.IController import IController
from future.interfaces.IMiddleware import IMiddleware
from future.middleware import AuthenticationMiddleware, ScopeValidationMiddleware
from future.request import Request
from future.response import Response
from future.routing import Get, RouteGroup
from future.testclient import FutureTestClient


class IUserRepository(Interface):
    def source(self) -> str:
        raise NotImplementedError


class DatabaseUserRepository(IUserRepository):
    def source(self) -> str:
        return "database"


class UserService:
    def __init__(self, users: IUserRepository) -> None:
        self.users = users


class InjectedController(IController):
    def __init__(self, request: Request, response: Response, users: UserService) -> None:
        super().__init__(request, response)
        self.users = users

    async def index(self) -> Response:
        return self.response.json({"source": self.users.users.source()})


class ConfiguredMiddleware(IMiddleware):
    def __init__(self, value: str) -> None:
        super().__init__()
        self.value = value

    async def before(self) -> Response | None:
        self.request.context["middleware"] = self.value
        return None


class MiddlewareController(IController):
    async def index(self) -> Response:
        return self.response.json({"middleware": self.request.context["middleware"]})


class AuthenticatedController(IController):
    async def index(self) -> Response:
        identity = self.request.identity
        assert identity is not None
        return self.response.json({"subject": identity.subject})


def base_config(**extra):
    return {"APP_NAME": "container-test", "APP_DOMAIN": "", "APP_DEBUG": False, "OPENAPI": {"enabled": False, "auto_routes": False}, **extra}


def basic_header(username: str, password: str) -> dict[str, str]:
    value = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"authorization": f"Basic {value}"}


async def test_controller_dependencies_are_resolved_from_bindings():
    app = Future(config=base_config(BINDINGS={IUserRepository: DatabaseUserRepository}))
    app.add_routes([Get("/users", InjectedController.index, "users")])
    async with FutureTestClient(app) as client:
        response = await client.get("http://127.0.0.1/users")
    assert response.status_code == 200
    assert response.json() == {"source": "database"}


async def test_configured_middleware_instances_are_request_bound_copies():
    definition = ConfiguredMiddleware("configured")
    app = Future(config=base_config())
    app.add_routes([Get("/middleware", MiddlewareController.index, "middleware", middlewares=[definition])])
    async with FutureTestClient(app) as client:
        response = await client.get("http://127.0.0.1/middleware")
    assert response.json() == {"middleware": "configured"}
    assert definition.request is None
    assert definition.response is None


async def test_authentication_identity_and_scopes_are_enforced():
    async def verify(username: str, password: str):
        if password != "secret":
            return None
        scopes = ("users:read",) if username == "reader" else ()
        return Identity(subject=username, provider="basic", scopes=scopes)

    config = base_config(AUTHENTICATION={"default": "basic", "providers": {"basic": {"driver": BasicAuthentication, "options": {"verify_credentials": verify}}}})
    authentication = AuthenticationMiddleware(provider="basic")
    app = Future(config=config)
    app.add_routes([RouteGroup(name="Authenticated", middlewares=[authentication, ScopeValidationMiddleware], routes=[Get("/users", AuthenticatedController.index, "users", scopes=["users:read"])])])
    async with FutureTestClient(app) as client:
        missing = await client.get("http://127.0.0.1/users")
        forbidden = await client.get("http://127.0.0.1/users", headers=basic_header("user", "secret"))
        allowed = await client.get("http://127.0.0.1/users", headers=basic_header("reader", "secret"))
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == 'Basic realm="Future"'
    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == {"subject": "reader"}
    assert authentication.request is None


def test_unbound_interfaces_report_the_dependency_chain():
    with pytest.raises(ResolutionError, match="No binding configured for IUserRepository"):
        Container().resolve(UserService)


def test_unknown_component_options_are_rejected():
    with pytest.raises(ResolutionError, match="Unknown configured option.*typo"):
        Container().resolve(BasicAuthentication, options={"verify_credentials": lambda _username, _password: True, "typo": True})


def test_identity_is_immutable_and_does_not_share_default_claims():
    first = Identity(subject="one", provider="test")
    second = Identity(subject="two", provider="test")
    first.claims["tenant"] = "one"

    assert second.claims == {}
    with pytest.raises(AttributeError, match="immutable"):
        first.subject = "changed"


async def test_components_start_in_order_and_stop_in_reverse():
    events = []

    class Component:
        def __init__(self, name):
            self.name = name

        async def start(self):
            events.append(f"start:{self.name}")

        async def stop(self):
            events.append(f"stop:{self.name}")

    container = Container()
    container.component(Component("one"))
    container.component(Component("two"))
    await container.start()
    await container.stop()
    assert events == ["start:one", "start:two", "stop:two", "stop:one"]
