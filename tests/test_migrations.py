from pathlib import Path

import pytest
from sqlalchemy import text

from future.database import Database
from future.databases.SQLiteDatabase import SQLiteDatabase
from future.interfaces.IModel import IModel
from future.migrations import Migrator, MigrationGenerator, Schema


class Widget(IModel):
    __connection__ = "default"
    __table__ = "widgets"
    id: str
    name: str


def _sqlite():
    Database._connections = {}
    Database._default = None
    Database().set_connection_details({"default": "sqlite", "sqlite": SQLiteDatabase(database=":memory:")})
    return Database().get_connection("default")


async def test_schema_create_and_drop_roundtrip():
    connection = _sqlite()
    Schema.connection("default")
    async with Schema.create("widgets") as table:
        table.id()
        table.string("name")
        table.integer("count").nullable()
        table.timestamps()
    assert await connection.table_exists("widgets") is True
    await Widget(id="1", name="w").save()
    found = await Widget.find("1")
    assert found is not None and found.name == "w"
    await Schema.drop("widgets")
    assert await connection.table_exists("widgets") is False
    await connection.disconnect()


async def test_schema_update_reconciles_columns_and_preserves_rows():
    connection = _sqlite()
    Schema.connection("default")
    async with Schema.create("widgets") as table:
        table.id()
        table.string("name")
    await Widget(id="1", name="kept").save()

    async with Schema.update("widgets") as table:
        table.id()
        table.string("name")
        table.integer("count").nullable()
    async with connection.client.connect() as database:
        columns = (await database.execute(text('PRAGMA table_info("widgets")'))).mappings().all()
    assert [column["name"] for column in columns] == ["id", "name", "count"]
    assert (await Widget.find("1")).name == "kept"

    async with Schema.update("widgets") as table:
        table.id()
        table.string("name")
    async with connection.client.connect() as database:
        columns = (await database.execute(text('PRAGMA table_info("widgets")'))).mappings().all()
    assert [column["name"] for column in columns] == ["id", "name"]
    assert (await Widget.find("1")).name == "kept"
    await connection.disconnect()


async def test_model_raises_when_table_missing():
    connection = _sqlite()
    with pytest.raises(RuntimeError, match="does not exist"):
        await Widget.find("1")
    await connection.disconnect()


async def test_migrator_run_is_idempotent_then_rollback(tmp_path):
    connection = _sqlite()
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "2026_01_01_create_widgets.py").write_text(
        "from future.migrations import Migration, Schema\n"
        "\n"
        "\n"
        "class CreateWidgets(Migration):\n"
        '    __connection__ = "default"\n'
        "\n"
        "    async def up(self):\n"
        '        async with Schema.create("widgets") as table:\n'
        "            table.id()\n"
        '            table.string("name")\n'
        "\n"
        "    async def down(self):\n"
        '        await Schema.drop("widgets")\n'
    )
    migrator = Migrator(path=str(mig_dir))
    assert await migrator.run() == ["2026_01_01_create_widgets"]
    assert await migrator.run() == []
    assert await connection.table_exists("widgets") is True
    assert await migrator.rollback() == ["2026_01_01_create_widgets"]
    assert await connection.table_exists("widgets") is False
    await connection.disconnect()


def test_migration_generator_skips_imodel_relations(tmp_path):
    framework_root = Path(__file__).resolve().parents[1]
    gen = MigrationGenerator(models_path=str(framework_root / "future" / "models"), migrations_path=str(tmp_path))
    paths = gen.make("PostModel")
    text = Path(paths[0]).read_text()
    assert "async def up" in text
    assert "async with Schema.create" in text
    assert 'table.string("title")' in text
    assert 'table.string("author_id")' in text
    assert 'table.string("author")' not in text


def test_migration_generator_uses_model_snapshots_for_updates_and_rollback(tmp_path):
    models = tmp_path / "models"
    migrations = tmp_path / "migrations"
    models.mkdir()
    model = models / "Widget.py"
    model.write_text(
        "from future.interfaces.IModel import IModel\n\n"
        "class Widget(IModel):\n"
        '    __table__ = "widgets"\n'
        "    id: str\n"
        "    name: str\n"
    )
    generator = MigrationGenerator(models_path=str(models), migrations_path=str(migrations))
    first = Path(generator.make("Widget")[0])
    assert "_create_widgets.py" in first.name
    assert 'Schema.create("widgets")' in first.read_text()

    model.write_text(model.read_text() + "    count: int | None\n")
    second = Path(generator.make("Widget")[0])
    rendered = second.read_text()
    assert "_update_widgets.py" in second.name
    assert rendered.count('Schema.update("widgets")') == 2
    up, down = rendered.split("    async def down(self):")
    assert 'table.integer("count").nullable()' in up
    assert 'table.integer("count")' not in down
    assert 'table.string("name")' in down


async def test_generated_update_migration_changes_table_and_rolls_back(tmp_path):
    connection = _sqlite()
    models = tmp_path / "models"
    migrations = tmp_path / "migrations"
    models.mkdir()
    model = models / "Widget.py"
    model.write_text(
        "from future.interfaces.IModel import IModel\n\n"
        "class Widget(IModel):\n"
        '    __table__ = "widgets"\n'
        "    id: str\n"
        "    name: str\n"
    )
    generator = MigrationGenerator(models_path=str(models), migrations_path=str(migrations))
    generator.make("Widget")
    migrator = Migrator(path=str(migrations))
    assert len(await migrator.run()) == 1
    await Widget(id="1", name="kept").save()

    model.write_text(model.read_text() + "    count: int | None\n")
    generator.make("Widget")
    assert len(await migrator.run()) == 1
    async with connection.client.connect() as database:
        columns = (await database.execute(text('PRAGMA table_info("widgets")'))).mappings().all()
    assert [column["name"] for column in columns] == ["id", "name", "count"]
    assert (await Widget.find("1")).name == "kept"

    assert len(await migrator.rollback()) == 1
    async with connection.client.connect() as database:
        columns = (await database.execute(text('PRAGMA table_info("widgets")'))).mappings().all()
    assert [column["name"] for column in columns] == ["id", "name"]
    assert (await Widget.find("1")).name == "kept"
    await connection.disconnect()


async def test_generated_update_backfills_new_required_model_field(tmp_path):
    connection = _sqlite()
    models = tmp_path / "models"
    migrations = tmp_path / "migrations"
    models.mkdir()
    model = models / "Widget.py"
    model.write_text(
        "from future.interfaces.IModel import IModel\n\n"
        "class Widget(IModel):\n"
        '    __table__ = "widgets"\n'
        "    id: str\n"
        "    name: str\n"
    )
    generator = MigrationGenerator(models_path=str(models), migrations_path=str(migrations))
    generator.make("Widget")
    migrator = Migrator(path=str(migrations))
    await migrator.run()
    await Widget(id="1", name="kept").save()

    model.write_text(model.read_text() + "    another_id: str\n")
    generator.make("Widget")
    assert len(await migrator.run()) == 1

    found = await Widget.find("1")
    assert found is not None
    assert found.name == "kept"
    assert found.another_id == ""
    async with connection.client.connect() as database:
        columns = (await database.execute(text('PRAGMA table_info("widgets")'))).mappings().all()
    another_id = next(column for column in columns if column["name"] == "another_id")
    assert another_id["notnull"] == 1
    await connection.disconnect()


def test_migration_generator_uses_model_field_default(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "Widget.py").write_text(
        "from future.interfaces.IModel import IModel\n\n"
        "class Widget(IModel):\n"
        '    __table__ = "widgets"\n'
        "    id: str\n"
        '    another_id: str = "unassigned"\n'
    )
    migration = Path(MigrationGenerator(models_path=str(models), migrations_path=str(tmp_path / "migrations")).make("Widget")[0]).read_text()
    assert 'table.string("another_id").default(\'unassigned\')' in migration
