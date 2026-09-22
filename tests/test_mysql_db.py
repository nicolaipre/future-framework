from unittest.mock import AsyncMock, MagicMock, patch

from future.databases.MySQLDatabase import MySQLDatabase
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


async def test_mysql_find():
    mysql = MySQLDatabase(host="localhost", port=3306, username="u", password="p", database="db")
    result = MagicMock()
    result.mappings.return_value.first.return_value = {"id": "1", "name": "n"}
    engine, connection = _engine_with_execute(result)
    mysql.client = engine

    found = await mysql.find(Row(), "1")
    assert found is not None and found.name == "n"
    assert "SELECT" in str(connection.execute.call_args[0][0])


async def test_mysql_get_builds_where_sql():
    mysql = MySQLDatabase(host="localhost", port=3306, username="u", password="p", database="db")
    result = MagicMock()
    result.mappings.return_value.all.return_value = [{"id": "2", "price": 9}]
    engine, connection = _engine_with_execute(result)
    mysql.client = engine

    rows = await mysql.get(Row(), wheres=[("price", ">", 1)], limit=10, orders=[("price", "desc")])
    assert len(rows) == 1 and rows[0].id == "2"
    sql = str(connection.execute.call_args[0][0])
    params = connection.execute.call_args[0][1]
    assert "price" in sql and ">" in sql
    assert params["v0"] == 1


async def test_mysql_connect_builds_url():
    with patch("future.databases.MySQLDatabase.create_async_engine") as create_async_engine:
        mysql = MySQLDatabase(host="h", port=3306, username="u", password="p", database="d")
        server = MagicMock()
        begin_cm = MagicMock()
        inner = MagicMock()
        inner.execute = AsyncMock()
        begin_cm.__aenter__ = AsyncMock(return_value=inner)
        begin_cm.__aexit__ = AsyncMock(return_value=None)
        server.begin = MagicMock(return_value=begin_cm)
        server.dispose = AsyncMock()
        create_async_engine.side_effect = [server, MagicMock()]
        await mysql.connect()
        urls = [call.args[0] for call in create_async_engine.call_args_list]
        assert any(url.endswith("/d") and "mysql+aiomysql://u:p@h:3306/d" == url for url in urls)
        assert any(url.endswith("/") for url in urls)


async def test_mysql_schema_update_uses_driver_specific_rebuild():
    mysql = MySQLDatabase(host="localhost", port=3306, username="u", password="p", database="db")
    mysql.table_exists = AsyncMock(return_value=True)
    result = MagicMock()
    result.mappings.return_value.all.return_value = [{"COLUMN_NAME": "id"}]
    engine, _ = _engine_with_execute(result)
    writer = MagicMock()
    writer.execute = AsyncMock()
    begin = MagicMock()
    begin.__aenter__ = AsyncMock(return_value=writer)
    begin.__aexit__ = AsyncMock(return_value=None)
    engine.begin = MagicMock(return_value=begin)
    mysql.client = engine
    blueprint = Blueprint("rows", "default", action="update")
    blueprint.id()
    blueprint.string("name")

    result = await mysql.schema_update(blueprint)

    sql = "\n".join(str(call.args[0]) for call in writer.execute.call_args_list)
    assert result["status"] == "updated"
    assert "CREATE TABLE `_future_migrate_rows`" in sql
    assert "SELECT COALESCE(`id`, :future_backfill_0), :future_backfill_1 FROM `rows`" in sql
    assert writer.execute.call_args_list[3].args[1]["future_backfill_1"] == ""
    assert "`_future_migrate_rows` TO `rows`" in sql
