from future.application import Future
from future.interfaces.IController import IController
from future.exceptions import HTTPException
from future.response import Response, StreamingResponse
from future.routing import Get, Post, RouteGroup
from future.lifespan import Lifespan
from future.testclient import FutureTestClient


class ParamController(IController):
    async def angle(self, item_id: str) -> Response:
        return self.response.json({"style": "angle", "item_id": item_id})

    async def mustache(self, item_id: str) -> Response:
        return self.response.json({"style": "mustache", "item_id": item_id})

    async def colon(self, item_id: str) -> Response:
        return self.response.json({"style": "colon", "item_id": item_id})

    async def boom(self) -> Response:
        raise HTTPException("nope", 422)

    async def ok(self) -> Response:
        return self.response.text("ok")

    async def chunks(self) -> Response:
        return StreamingResponse(["hello", " ", "world"], content_type="text/plain")

    async def ab(self):
        yield b"a"
        yield b"b"

    async def async_chunks(self) -> Response:
        return StreamingResponse(self.ab(), content_type="text/plain")


def _app():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([
        RouteGroup(
            name="Main",
            routes=[
                Get("/angle/<int:item_id>", ParamController.angle, "angle"),
                Get("/mustache/{item_id}", ParamController.mustache, "mustache"),
                Get("/colon/:item_id", ParamController.colon, "colon"),
                Get("/same", ParamController.ok, "same.get"),
                Post("/same", ParamController.ok, "same.post"),
                Get("/boom", ParamController.boom, "boom"),
                Get("/stream", ParamController.chunks, "stream"),
                Get("/async-stream", ParamController.async_chunks, "async-stream"),
            ],
        )
    ])
    return app


async def test_path_param_styles():
    async with FutureTestClient(_app()) as client:
        r = await client.get("http://127.0.0.1/angle/7")
        assert r.status_code == 200 and r.json() == {"style": "angle", "item_id": "7"}
        r = await client.get("http://127.0.0.1/mustache/abc")
        assert r.status_code == 200 and r.json()["style"] == "mustache"
        r = await client.get("http://127.0.0.1/colon/xyz")
        assert r.status_code == 200 and r.json()["item_id"] == "xyz"


async def test_multi_method_and_405():
    async with FutureTestClient(_app()) as client:
        assert (await client.get("http://127.0.0.1/same")).status_code == 200
        assert (await client.post("http://127.0.0.1/same")).status_code == 200
        r = await client.client.put("http://127.0.0.1/same")
        assert r.status_code == 405
        assert "GET" in r.headers.get("allow", "")


async def test_http_exception_json():
    async with FutureTestClient(_app()) as client:
        r = await client.get("http://127.0.0.1/boom")
        assert r.status_code == 422
        assert r.json()["error"] == "nope"


async def test_debug_strips_host_port():
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "t", "APP_DOMAIN": "localhost", "APP_DEBUG": True, "OPENAPI": {"enabled": False, "auto_routes": False}})
    app.add_routes([RouteGroup(name="Main", routes=[Get("/x", ParamController.ok, "x")])])
    # domainless false — routes keyed under localhost
    assert "localhost" in app.routes or any("localhost" in d for d in app.routes)
    async with FutureTestClient(app) as client:
        r = await client.get("http://127.0.0.1/x", headers={"host": "localhost:8000"})
        # With APP_DEBUG, Host port stripped so domain check passes
        assert r.status_code in (200, 404)
        # If 404, domain key mismatch for registration — registration uses APP_DOMAIN without port
        # Re-check: routes registered under subdomain "" + domain localhost = "localhost"
        r2 = await client.get("http://127.0.0.1/x", headers={"host": "localhost"})
        assert r2.status_code == 200
        r3 = await client.get("http://127.0.0.1/x", headers={"host": "localhost:8000"})
        assert r3.status_code == 200


async def test_404_not_found_json():
    async with FutureTestClient(_app()) as client:
        r = await client.get("http://127.0.0.1/no-such-route")
        assert r.status_code == 404
        assert r.json()["error"] == "Not Found"


async def test_response_helpers():
    from future.response import Response
    json_response = Response().json({"ok": True}, status=201)
    assert json_response.status == 201
    assert json_response.body == b'{"ok": true}'
    html_response = Response().html("<p>hi</p>")
    assert html_response.status == 200
    assert any(pair[1] == b"text/html" for pair in html_response.headers)
    empty = Response().empty()
    assert empty.status == 204
    redirect = Response().redirect("/next")
    assert redirect.status == 302
    assert any(pair[0] == b"location" and pair[1] == b"/next" for pair in redirect.headers)
    cookie = Response().text("ok")
    cookie.set_cookie("sid", "1")
    cookie.delete_cookie("sid")
    names = [pair[1].decode() for pair in cookie.headers if pair[0] == b"set-cookie"]
    assert any(value.startswith("sid=1") for value in names)
    assert any("Max-Age=0" in value for value in names)
    streamed = StreamingResponse(["a", "b"], content_type="text/plain")
    assert streamed.status == 200
    assert streamed._chunks == ["a", "b"]


async def test_streaming_response_concatenates_chunks():
    async with FutureTestClient(_app()) as client:
        response = await client.get("http://127.0.0.1/stream")
        assert response.status_code == 200
        assert response.text == "hello world"
        async_response = await client.get("http://127.0.0.1/async-stream")
        assert async_response.status_code == 200
        assert async_response.text == "ab"
