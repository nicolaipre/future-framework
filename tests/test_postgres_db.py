from unittest.mock import AsyncMock, MagicMock, patch

from future.databases.PostgresDatabase import PostgresDatabase
from future.interfaces.IModel import IModel
from future.migrations import Blueprint


class Row(IModel):
    __table__ = "rows"


def _engine_with_execute(result):
    connection = MagicMock()
    connection.execute = AsyncMock(return_value=result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=connection)
    cm.__aexit__ = AsyncMock(return_value=None)
    engine = MagicMock()
    engine.connect = MagicMock(return_value=cm)
    return engine, connection


async def test_postgres_find():
    postgres = PostgresDatabase(host="localhost", port=5432, username="u", password="p", database="db")
    result = MagicMock()
    result.mappings.return_value.first.return_value = {"id": "1", "name": "n"}
    engine, connection = _engine_with_execute(result)
    postgres.client = engine

    found = await postgres.find(Row(), "1")
    assert found is not None and found.name == "n"
    assert "SELECT" in str(connection.execute.call_args[0][0])


async def test_postgres_get_builds_where_sql():
    postgres = PostgresDatabase(host="localhost", port=5432, username="u", password="p", database="db")
    result = MagicMock()
    result.mappings.return_value.all.return_value = [{"id": "2", "price": 9}]
    engine, connection = _engine_with_execute(result)
    postgres.client = engine

    rows = await postgres.get(Row(), wheres=[("price", ">", 1)], limit=10, orders=[("price", "desc")])
    assert len(rows) == 1 and rows[0].id == "2"
    sql = str(connection.execute.call_args[0][0])
    params = connection.execute.call_args[0][1]
    assert "price" in sql and ">" in sql
    assert params["v0"] == 1


async def test_postgres_connect_builds_url():
    with patch("future.databases.PostgresDatabase.create_async_engine") as create_async_engine:
        postgres = PostgresDatabase(host="h", port=5432, username="u", password="p@ss", database="d")
        create_async_engine.return_value = MagicMock()
        await postgres.connect()
        url = create_async_engine.call_args[0][0]
        assert url == "postgresql+asyncpg://u:p%40ss@h:5432/d"


async def test_postgres_schema_update_uses_driver_specific_rebuild():
    postgres = PostgresDatabase(host="localhost", port=5432, username="u", password="p", database="db")
    postgres.table_exists = AsyncMock(return_value=True)
    result = MagicMock()
    result.mappings.return_value.all.return_value = [{"column_name": "id"}]
    engine, _ = _engine_with_execute(result)
    writer = MagicMock()
    writer.execute = AsyncMock()
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=writer)
    begin.__aexit__ = AsyncMock(return_value=None)
    engine.begin = MagicMock(return_value=begin)
    postgres.client = engine
    blueprint = Blueprint("rows", "default", action="update")
    blueprint.id()
    blueprint.string("name")

    result = await postgres.schema_update(blueprint)

    sql = "\n".join(str(call.args[0]) for call in writer.execute.call_args_list)
    assert result["status"] == "updated"
    assert 'CREATE TABLE "_future_' in sql
    assert 'SELECT COALESCE("id", :future_backfill_0), :future_backfill_1 FROM "rows"' in sql
    assert writer.execute.call_args_list[2].args[1]["future_backfill_1"] == ""
    assert 'RENAME TO "rows"' in sql
