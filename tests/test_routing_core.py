from typing import Optional

import pytest

from future.application import Future
from future.interfaces.IController import IController
from future.interfaces.IMiddleware import IMiddleware
from future.lifespan import Lifespan
from future.response import Response
from future.routing import Delete, Get, Head, InvalidValuePatternName, Options, Patch, Post, Put, Route, RouteException, RouteGroup
from future.testclient import FutureTestClient


class VerbController(IController):
    async def echo(self) -> Response:
        payload = {"method": self.request.method, "path": self.request.path}
        if (self.request.headers.get("content-type") or "").startswith("application/json"):
            payload["body"] = await self.request.json()
        return self.response.json(payload)

    async def item(self, item_id: str) -> Response:
        return self.response.json({"item_id": item_id})

    async def amount(self, amount: str) -> Response:
        return self.response.json({"amount": amount})

    async def file(self, rest: str) -> Response:
        return self.response.json({"rest": rest})

    async def tail(self, tail: str) -> Response:
        return self.response.json({"tail": tail})


class MarkMiddleware(IMiddleware):
    name = "mark"

    async def after(self) -> Optional[Response]:
        self.response.headers.append([b"x-mark", b"1"])
        return None


class OrderMiddleware(IMiddleware):
    name = "order"

    async def before(self) -> Optional[Response]:
        self.request.context.setdefault("hops", []).append(self.name)
        return None


async def test_all_http_methods_echo_method_and_body():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(
            name="Verbs",
            prefix="/verbs",
            routes=[
                Get("/echo", VerbController.echo, "get"),
                Post("/echo", VerbController.echo, "post"),
                Put("/echo", VerbController.echo, "put"),
                Patch("/echo", VerbController.echo, "patch"),
                Delete("/echo", VerbController.echo, "delete"),
                Head("/echo", VerbController.echo, "head"),
                Options("/echo", VerbController.echo, "options"),
            ],
        )
    ])
    async with FutureTestClient(app) as client:
        get = await client.get("http://127.0.0.1/verbs/echo")
        assert get.status_code == 200 and get.json() == {"method": "GET", "path": "/verbs/echo"}
        post = await client.post("http://127.0.0.1/verbs/echo", json={"n": 1})
        assert post.status_code == 200 and post.json() == {"method": "POST", "path": "/verbs/echo", "body": {"n": 1}}
        put = await client.client.put("http://127.0.0.1/verbs/echo", json={"n": 2})
        assert put.status_code == 200 and put.json() == {"method": "PUT", "path": "/verbs/echo", "body": {"n": 2}}
        patch = await client.client.patch("http://127.0.0.1/verbs/echo", json={"n": 3})
        assert patch.status_code == 200 and patch.json() == {"method": "PATCH", "path": "/verbs/echo", "body": {"n": 3}}
        delete = await client.client.delete("http://127.0.0.1/verbs/echo")
        assert delete.status_code == 200 and delete.json() == {"method": "DELETE", "path": "/verbs/echo"}
        head = await client.client.head("http://127.0.0.1/verbs/echo")
        assert head.status_code == 200
        options = await client.client.request("OPTIONS", "http://127.0.0.1/verbs/echo")
        assert options.status_code == 200 and options.json()["method"] == "OPTIONS"


async def test_multi_method_route_and_405_allow_header():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([Route(methods=["GET", "POST"], path="/share", endpoint=VerbController.echo, name="share")])
    async with FutureTestClient(app) as client:
        assert (await client.get("http://127.0.0.1/share")).json()["method"] == "GET"
        assert (await client.post("http://127.0.0.1/share", json={})).json()["method"] == "POST"
        denied = await client.client.patch("http://127.0.0.1/share")
        assert denied.status_code == 405
        allow = denied.headers.get("allow", "")
        assert "GET" in allow and "POST" in allow
        assert denied.json()["error"] == "Method Not Allowed"


async def test_head_and_options_on_get_only_are_405():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([Get("/only-get", VerbController.echo, "only")])
    async with FutureTestClient(app) as client:
        assert (await client.get("http://127.0.0.1/only-get")).status_code == 200
        for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            response = await client.client.request(method, "http://127.0.0.1/only-get")
            assert response.status_code == 405, method
            assert "GET" in response.headers.get("allow", "")


async def test_nested_prefixes_and_unknown_prefix_404():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(
            name="Api",
            prefix="/api",
            routes=[
                RouteGroup(
                    name="V1",
                    prefix="/v1",
                    routes=[Get("/items", VerbController.echo, "items"), Get("/", VerbController.echo, "v1root")],
                )
            ],
        )
    ])
    async with FutureTestClient(app) as client:
        items = await client.get("http://127.0.0.1/api/v1/items")
        assert items.status_code == 200 and items.json()["path"] == "/api/v1/items"
        root = await client.get("http://127.0.0.1/api/v1")
        assert root.status_code == 200 and root.json()["path"] == "/api/v1"
        assert (await client.get("http://127.0.0.1/v1/items")).status_code == 404
        assert (await client.get("http://127.0.0.1/api/items")).status_code == 404


async def test_prefix_and_subdomain_and_middleware_together():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "example.com", "APP_DEBUG": False, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(
            name="Api",
            subdomain="api",
            prefix="/v2",
            middlewares=[MarkMiddleware],
            routes=[Get("/status", VerbController.echo, "status")],
        )
    ])
    async with FutureTestClient(app) as client:
        ok = await client.get("http://127.0.0.1/v2/status", headers={"Host": "api.example.com"})
        assert ok.status_code == 200
        assert ok.json()["path"] == "/v2/status"
        assert ok.headers.get("x-mark") == "1"
        assert (await client.get("http://127.0.0.1/v2/status", headers={"Host": "example.com"})).status_code == 404
        assert (await client.get("http://127.0.0.1/status", headers={"Host": "api.example.com"})).status_code == 404


async def test_nested_subdomains():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "example.com", "APP_DEBUG": False, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(
            name="Api",
            subdomain="api",
            routes=[
                RouteGroup(name="V1", subdomain="v1", routes=[Get("/ping", VerbController.echo, "ping")]),
            ],
        )
    ])
    async with FutureTestClient(app) as client:
        ok = await client.get("http://127.0.0.1/ping", headers={"Host": "v1.api.example.com"})
        assert ok.status_code == 200 and ok.json()["method"] == "GET"
        assert (await client.get("http://127.0.0.1/ping", headers={"Host": "api.example.com"})).status_code == 404
        assert (await client.get("http://127.0.0.1/ping", headers={"Host": "v1.example.com"})).status_code == 404


async def test_unknown_host_and_other_subdomain_are_404():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "example.com", "APP_DEBUG": False, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([RouteGroup(name="Www", subdomain="www", routes=[Get("/home", VerbController.echo, "home")])])
    async with FutureTestClient(app) as client:
        unknown_host = await client.get("http://127.0.0.1/home", headers={"Host": "evil.com"})
        assert unknown_host.status_code == 404
        assert unknown_host.json()["error"] == "Not Found"
        missing = await client.get("http://127.0.0.1/home", headers={"Host": "api.example.com"})
        assert missing.status_code == 404


async def test_domainless_mode_ignores_subdomain_keeps_prefix():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([RouteGroup(name="Api", subdomain="api", prefix="/svc", routes=[Get("/ok", VerbController.echo, "ok")])])
    assert "" in app.routes
    async with FutureTestClient(app) as client:
        first = await client.get("http://127.0.0.1/svc/ok", headers={"Host": "anything.local"})
        assert first.status_code == 200
        second = await client.get("http://127.0.0.1/svc/ok")
        assert second.status_code == 200


def test_domainless_mode_same_path_on_different_subdomains_conflicts():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    with pytest.raises(ValueError, match="domainless mode"):
        app.add_routes([
            RouteGroup(name="Api", subdomain="api", prefix="/v1", routes=[Get("/users", VerbController.echo, "api-users")]),
            RouteGroup(name="Www", subdomain="www", prefix="/v1", routes=[Get("/users", VerbController.echo, "www-users")]),
        ])


def test_domainless_mode_different_prefixes_do_not_conflict():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(name="Api", subdomain="api", prefix="/api", routes=[Get("/users", VerbController.echo, "api-users")]),
        RouteGroup(name="Www", subdomain="www", prefix="/www", routes=[Get("/users", VerbController.echo, "www-users")]),
    ])
    assert app.has_path("/api/users")
    assert app.has_path("/www/users")


async def test_route_and_group_middleware_stack():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(
            name="Outer",
            prefix="/mw",
            middlewares=[OrderMiddleware],
            routes=[Get("/x", VerbController.echo, "x", middlewares=[MarkMiddleware])],
        )
    ])
    async with FutureTestClient(app) as client:
        response = await client.get("http://127.0.0.1/mw/x")
        assert response.status_code == 200
        assert response.headers.get("x-mark") == "1"


async def test_path_param_int_float_uuid_path_and_wildcard():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        Get("/items/<int:item_id>", VerbController.item, "item"),
        Get("/price/<float:amount>", VerbController.amount, "price"),
        Get("/users/<uuid:item_id>", VerbController.item, "user"),
        Get("/files/<path:rest>", VerbController.file, "file"),
        Get("/static/*", VerbController.tail, "static"),
    ])
    async with FutureTestClient(app) as client:
        assert (await client.get("http://127.0.0.1/items/9")).json() == {"item_id": "9"}
        assert (await client.get("http://127.0.0.1/items/nope")).status_code == 404
        assert (await client.get("http://127.0.0.1/price/1.5")).json() == {"amount": "1.5"}
        uid = "550e8400-e29b-41d4-a716-446655440000"
        assert (await client.get(f"http://127.0.0.1/users/{uid}")).json() == {"item_id": uid}
        assert (await client.get("http://127.0.0.1/users/not-a-uuid")).status_code == 404
        assert (await client.get("http://127.0.0.1/files/a/b/c.txt")).json() == {"rest": "a/b/c.txt"}
        wild = await client.get("http://127.0.0.1/static/css/app.css")
        assert wild.status_code == 200
        assert "css/app.css" in wild.json()["tail"] or wild.json()["tail"].endswith("css/app.css")


def test_compile_pattern_rejects_bad_patterns():
    bad_name = Get("/x/<nope:id>", VerbController.echo, "bad")
    with pytest.raises(InvalidValuePatternName):
        bad_name.compile_pattern()
    two_stars = Get("/a/*/b/*", VerbController.echo, "stars")
    with pytest.raises(RouteException):
        two_stars.compile_pattern()
    dup = Get("/x/<id>/y/<id>", VerbController.echo, "dup")
    with pytest.raises(ValueError, match="multiple parameters"):
        dup.compile_pattern()


def test_strict_slashes_does_not_match_trailing_slash():
    loose = Get("/exact", VerbController.echo, "loose")
    loose.compile_pattern()
    assert loose.match("GET", b"/exact") is not None
    assert loose.match("GET", b"/exact/") is not None
    strict = Get("/exact", VerbController.echo, "strict", strict_slashes=True)
    strict.compile_pattern()
    assert strict.match("GET", b"/exact") is not None
    assert strict.match("GET", b"/exact/") is None


def test_route_group_validation_and_conflicts():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "example.com", "APP_DEBUG": False, "OPENAPI": {"enabled": False, "auto_routes": False}})
    with pytest.raises(ValueError, match="prefix"):
        app.add_routes([RouteGroup(name="Bad", prefix="api", routes=[Get("/x", VerbController.echo, "x")])])
    with pytest.raises(ValueError, match="prefix"):
        app.add_routes([RouteGroup(name="Bad", prefix="/api//v1", routes=[Get("/x", VerbController.echo, "x")])])
    with pytest.raises(ValueError, match="subdomain"):
        app.add_routes([RouteGroup(name="Bad", subdomain="api_v1", routes=[Get("/x", VerbController.echo, "x")])])
    with pytest.raises(ValueError, match="conflict"):
        app.add_routes([Get("/dup", VerbController.echo, "a"), Get("/dup", VerbController.echo, "b")])
    app.add_routes([Get("/ok", VerbController.echo, "get"), Post("/ok", VerbController.echo, "post")])
    assert app.has_path("/ok")
    stats = app.get_performance_stats()
    assert stats["total_routes"] >= 2
    assert "example.com" in stats["domain_list"]


def test_invalid_app_domain_rejected():
    with pytest.raises(ValueError, match="domain"):
        Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "bad_domain", "APP_DEBUG": False})


async def test_nested_prefix_and_subdomain_all_write_methods():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "example.com", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(
            name="Api",
            subdomain="api",
            prefix="/api",
            routes=[
                RouteGroup(
                    name="Admin",
                    subdomain="admin",
                    prefix="/admin",
                    routes=[
                        Post("/users", VerbController.echo, "create"),
                        Put("/users", VerbController.echo, "replace"),
                        Patch("/users", VerbController.echo, "update"),
                        Delete("/users", VerbController.echo, "remove"),
                    ],
                )
            ],
        )
    ])
    host = {"Host": "admin.api.example.com:8000"}
    url = "http://127.0.0.1/api/admin/users"
    async with FutureTestClient(app) as client:
        post = await client.post(url, json={"name": "Ada"}, headers=host)
        assert post.status_code == 200 and post.json()["body"] == {"name": "Ada"}
        put = await client.client.put(url, json={"name": "Bob"}, headers=host)
        assert put.status_code == 200 and put.json()["method"] == "PUT"
        patch = await client.client.patch(url, json={"name": "Cara"}, headers=host)
        assert patch.status_code == 200 and patch.json()["method"] == "PATCH"
        delete = await client.client.delete(url, headers=host)
        assert delete.status_code == 200 and delete.json()["method"] == "DELETE"
        assert (await client.get(url, headers=host)).status_code == 405
        assert (await client.post(url, json={}, headers={"Host": "api.example.com"})).status_code == 404


async def test_hyphen_subdomain_and_trailing_slash():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "example.com", "APP_DEBUG": False, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([RouteGroup(name="Docs", subdomain="my-app", prefix="/docs", routes=[Get("/health", VerbController.echo, "health")])])
    async with FutureTestClient(app) as client:
        slashed = await client.get("http://127.0.0.1/docs/health/", headers={"Host": "my-app.example.com"})
        assert slashed.status_code == 200
        assert slashed.json()["path"] == "/docs/health/"


def test_route_match_rejects_other_method():
    route = Get("/only", VerbController.echo, "only")
    route.compile_pattern()
    assert route.match("GET", b"/only") is not None
    assert route.match("POST", b"/only") is None
    assert route.match("GET", b"/other") is None
