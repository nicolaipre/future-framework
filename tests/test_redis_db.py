from unittest.mock import AsyncMock, MagicMock, patch

from future.databases.RedisDatabase import RedisDatabase
from future.interfaces.IModel import IModel
from future.migrations import Blueprint


class Row(IModel):
    __table__ = "rows"


async def test_redis_save_find():
    redis = RedisDatabase(host="localhost", port=6379, username="", password="", database="0")
    client = MagicMock()
    client.set = AsyncMock()
    client.sadd = AsyncMock()
    client.get = AsyncMock(return_value='{"id": "1", "name": "n"}')
    redis.client = client
    result = await redis.save(Row(id="1", name="n"))
    assert result["status"] == "saved"
    client.set.assert_awaited()
    found = await redis.find(Row(), "1")
    assert found is not None and found.name == "n"


async def test_redis_find_missing_returns_none():
    redis = RedisDatabase(host="localhost", port=6379, username="", password="", database="0")
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    redis.client = client
    assert await redis.find(Row(), "missing") is None


async def test_redis_get_filters_in_memory():
    redis = RedisDatabase(host="localhost", port=6379, username="", password="", database="0")
    redis.all = AsyncMock(return_value=[Row(id="1", name="a", price=1), Row(id="2", name="b", price=9)])
    redis.client = MagicMock()
    rows = await redis.get(Row(), wheres=[("price", ">", 5)], limit=1, orders=[("price", "desc")])
    assert len(rows) == 1 and rows[0].id == "2"


async def test_redis_connect_uses_asyncio_client():
    with patch("redis.asyncio.Redis") as redis_cls:
        client = MagicMock()
        client.ping = AsyncMock()
        redis_cls.return_value = client
        redis = RedisDatabase(host="h", port=6379, username="", password="", database="2")
        await redis.connect()
        redis_cls.assert_called()
        assert redis_cls.call_args.kwargs["db"] == 2
        client.ping.assert_awaited()


async def test_redis_supports_schema_snapshots_and_migration_history():
    redis = RedisDatabase(host="localhost", port=6379, username="", password="", database="0")
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    client.zadd = AsyncMock()
    client.zrange = AsyncMock(return_value=["001_create_rows"])
    client.zscore = AsyncMock(return_value=2.0)
    client.zrevrange = AsyncMock(return_value=[("001_create_rows", 2.0)])
    redis.client = client
    blueprint = Blueprint("rows", "default", action="update")
    blueprint.id()
    blueprint.string("name")

    result = await redis.schema_update(blueprint)
    await redis.migrations_put("001_create_rows", 2)

    assert result["status"] == "updated"
    assert "\"name\": \"name\"" in client.set.call_args.args[1]
    assert await redis.migrations_get() == ["001_create_rows"]
    assert await redis.migrations_max_batch() == 2
    assert await redis.migrations_batch_for("001_create_rows") == 2
