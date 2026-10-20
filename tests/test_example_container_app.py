import base64

from future.testclient import FutureTestClient

from examples.container_app.app.repositories.IUserRepository import IUserRepository
from examples.container_app.run import create_app


def basic_header(username: str, password: str) -> dict[str, str]:
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"authorization": f"Basic {credentials}"}


async def test_container_example_application_resolves_dependencies_and_enforces_scopes():
    app = create_app()

    async with FutureTestClient(app) as client:
        health = await client.get("http://127.0.0.1/health")
        unauthenticated = await client.get("http://127.0.0.1/users/1")
        reader = await client.get("http://127.0.0.1/users/1", headers=basic_header("reader", "secret"))
        forbidden = await client.get("http://127.0.0.1/users/1/admin", headers=basic_header("reader", "secret"))
        admin = await client.get("http://127.0.0.1/users/1/admin", headers=basic_header("admin", "secret"))

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == 'Basic realm="Future container example"'
    assert reader.status_code == 200
    assert reader.json() == {"user": {"id": "1", "name": "Ada", "source": "memory"}, "identity": "reader", "audit": "GET /users/1"}
    assert forbidden.status_code == 403
    assert admin.status_code == 200
    assert admin.json()["admin"] is True


async def test_container_example_application_accepts_test_overrides():
    class FakeUserRepository:
        async def find(self, user_id: str) -> dict[str, str] | None:
            return {"id": user_id, "name": "Test user", "source": "override"}

    app = create_app()
    app.override(IUserRepository, FakeUserRepository())

    async with FutureTestClient(app) as client:
        response = await client.get("http://127.0.0.1/users/99", headers=basic_header("reader", "secret"))

    assert response.status_code == 200
    assert response.json()["user"] == {"id": "99", "name": "Test user", "source": "override"}
