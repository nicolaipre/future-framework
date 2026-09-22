# Migrations — Orator/Masonite-style schema, discovery, and generation.


import ast
import importlib.util
import inflection

from datetime import datetime
from pathlib import Path
from types import UnionType
from typing import get_args, get_origin, Union

from future.database import Database
from future.interfaces.IModel import IModel


class Migration:
    __connection__ = "default"

    def up(self):
        raise NotImplementedError

    def down(self):
        raise NotImplementedError


class Column:
    def __init__(self, name, type, length=None):
        self.name = name
        self.type = type
        self.length = length
        self.is_nullable = False
        self.is_unique = False
        self.is_primary = False
        self.is_index = False
        self.default_value = None

    def nullable(self):
        self.is_nullable = True
        return self

    def unique(self):
        self.is_unique = True
        return self

    def primary(self):
        self.is_primary = True
        return self

    def index(self):
        self.is_index = True
        return self

    def default(self, value):
        self.default_value = value
        return self


class Blueprint:
    def __init__(self, name, connection_name, action="create"):
        self.name = name
        self.connection_name = connection_name
        self.action = action
        self.columns = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            return False
        connection = Database().get_connection(self.connection_name)
        if self.action == "create":
            await connection.schema_create(self)
        elif self.action == "update":
            await connection.schema_update(self)
        return False

    def _add(self, column):
        self.columns.append(column)
        return column

    def id(self):
        return self._add(Column("id", "string", length=255)).primary()

    def string(self, name, length=255):
        return self._add(Column(name, "string", length=length))

    def text(self, name):
        return self._add(Column(name, "text"))

    def integer(self, name):
        return self._add(Column(name, "integer"))

    def float(self, name):
        return self._add(Column(name, "float"))

    def boolean(self, name):
        return self._add(Column(name, "boolean"))

    def datetime(self, name):
        return self._add(Column(name, "datetime"))

    def timestamps(self):
        self.datetime("created_at").nullable()
        self.datetime("updated_at").nullable()
        return self


class SchemaMeta(type):
    def connection(cls, name):
        cls._connection_name = name
        return cls

    def create(cls, name):
        return Blueprint(name, cls._connection_name, action="create")

    def update(cls, name):
        return Blueprint(name, cls._connection_name, action="update")

    async def drop(cls, name):
        await Database().get_connection(cls._connection_name).schema_drop(name)


class Schema(metaclass=SchemaMeta):
    _connection_name = "default"


class Migrator:
    def __init__(self, path):
        self.path = path

    def discover(self):
        migrations = []
        directory = Path(self.path)
        if not directory.exists():
            return migrations
        for file_path in sorted(directory.glob("*.py")):
            if file_path.name.startswith("_"):
                continue
            module_name = f"migration_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for value in module.__dict__.values():
                if isinstance(value, type) and issubclass(value, Migration) and value is not Migration:
                    migrations.append((file_path.stem, value))
                    break
        return migrations

    async def run(self):
        applied_by_connection = {}
        batch_by_connection = {}
        ran = []
        for name, migration_class in self.discover():
            migration = migration_class()
            connection_name = getattr(migration, "__connection__", "default")
            connection = Database().get_connection(connection_name)
            if connection_name not in applied_by_connection:
                applied_by_connection[connection_name] = set(await connection.migrations_get())
                batch_by_connection[connection_name] = await connection.migrations_max_batch() + 1
            if name in applied_by_connection[connection_name]:
                continue
            Schema.connection(connection_name)
            await migration.up()
            await connection.migrations_put(name, batch_by_connection[connection_name])
            ran.append(name)
        return ran

    async def rollback(self):
        rolled = []
        by_connection = {}
        for name, migration_class in self.discover():
            migration = migration_class()
            connection_name = getattr(migration, "__connection__", "default")
            by_connection.setdefault(connection_name, []).append((name, migration))
        for connection_name, items in by_connection.items():
            connection = Database().get_connection(connection_name)
            max_batch = await connection.migrations_max_batch()
            if max_batch == 0:
                continue
            for name, migration in reversed(items):
                if await connection.migrations_batch_for(name) != max_batch:
                    continue
                Schema.connection(connection_name)
                await migration.down()
                await connection.migrations_delete(name)
                rolled.append(name)
        return rolled


class MigrationGenerator:
    def __init__(self, models_path="app/models", migrations_path="database/migrations"):
        self.models_path = models_path
        self.migrations_path = migrations_path

    def find_model(self, name):
        for model in self.discover_models():
            if model.__name__ == name:
                return model
        raise ValueError(f"IModel not found: {name}")

    def discover_models(self):
        directory = Path(self.models_path)
        if not directory.exists():
            raise FileNotFoundError(f"Models path not found: {self.models_path}")
        models = []
        seen = set()
        for file_path in sorted(directory.glob("*.py")):
            if file_path.name.startswith("_"):
                continue
            module_name = f"app_model_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for value in module.__dict__.values():
                if not isinstance(value, type) or not issubclass(value, IModel) or value is IModel:
                    continue
                if value.__name__ in seen:
                    continue
                if not getattr(value, "__annotations__", None):
                    continue
                seen.add(value.__name__)
                models.append(value)
        return models

    def table_name(self, model):
        return model.__table__ or inflection.tableize(model.__name__)

    def column_line(self, field, annotation):
        nullable = False
        origin = get_origin(annotation)
        if origin is Union or origin is UnionType:
            args = get_args(annotation)
            nullable = type(None) in args
            non_null = [arg for arg in args if arg is not type(None)]
            annotation = non_null[0] if non_null else str
        if field == "id":
            return "table.id()"
        if isinstance(annotation, type) and issubclass(annotation, IModel):
            return None
        type_name = getattr(annotation, "__name__", str(annotation))
        if annotation is datetime or type_name == "datetime":
            line = f'table.datetime("{field}")'
        elif annotation is int or type_name == "int":
            line = f'table.integer("{field}")'
        elif annotation is float or type_name == "float":
            line = f'table.float("{field}")'
        elif annotation is bool or type_name == "bool":
            line = f'table.boolean("{field}")'
        elif field in ("description", "text", "body", "content") or field.endswith("_original") or field.endswith("_translated"):
            line = f'table.text("{field}")'
        else:
            line = f'table.string("{field}")'
        if nullable:
            line += ".nullable()"
        return line

    def blueprint_lines(self, model):
        annotations = dict(getattr(model, "__annotations__", {}))
        lines = []
        if "created_at" in annotations and "updated_at" in annotations:
            annotations.pop("created_at")
            annotations.pop("updated_at")
            use_timestamps = True
        else:
            use_timestamps = False
        for field, annotation in annotations.items():
            line = self.column_line(field, annotation)
            if line is not None:
                lines.append(f"            {line}")
        if use_timestamps:
            lines.append("            table.timestamps()")
        return lines

    def _schema_call(self, node, table):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr not in ("create", "update") or not isinstance(node.func.value, ast.Name) or node.func.value.id != "Schema":
            return False
        return bool(node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == table)

    def _previous_blueprint_lines(self, table):
        directory = Path(self.migrations_path)
        if not directory.exists():
            return None
        for path in reversed(sorted(directory.glob("*.py"))):
            try:
                source = path.read_text()
                tree = ast.parse(source)
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.AsyncFunctionDef) or node.name != "up":
                    continue
                for statement in node.body:
                    if not isinstance(statement, ast.AsyncWith):
                        continue
                    if not statement.items or not self._schema_call(statement.items[0].context_expr, table):
                        continue
                    lines = []
                    for item in statement.body:
                        if not isinstance(item, ast.Expr) or not isinstance(item.value, ast.Call):
                            continue
                        expression = (ast.get_source_segment(source, item) or ast.unparse(item)).strip()
                        if expression.startswith("table."):
                            lines.append(f"            {expression}")
                    return lines
        return None

    def render(self, model, previous_lines=None):
        table = self.table_name(model)
        is_update = previous_lines is not None
        action = "update" if is_update else "create"
        class_name = f"{'Update' if is_update else 'Create'}{inflection.camelize(table)}"
        connection = getattr(model, "__connection__", "default")
        columns = "\n".join(self.blueprint_lines(model))
        rendered = (
            "from future.migrations import Migration, Schema\n"
            "\n"
            "\n"
            f"class {class_name}(Migration):\n"
            f'    __connection__ = "{connection}"\n'
            "\n"
            "    async def up(self):\n"
            f'        async with Schema.{action}("{table}") as table:\n'
            f"{columns}\n"
            "\n"
        )
        if not is_update:
            return rendered + "    async def down(self):\n" + f'        await Schema.drop("{table}")\n'
        previous = "\n".join(previous_lines)
        return rendered + "    async def down(self):\n" + f'        async with Schema.update("{table}") as table:\n' + f"{previous}\n"

    def make(self, model_name=None):
        if model_name is None:
            return self.make_all()
        model = self.find_model(model_name)
        return [self.write(model)]

    def make_all(self):
        paths = []
        for index, model in enumerate(self.discover_models()):
            paths.append(self.write(model, stamp_offset=index))
        return paths

    def write(self, model, stamp_offset=0):
        table = self.table_name(model)
        previous_lines = self._previous_blueprint_lines(table)
        action = "update" if previous_lines is not None else "create"
        stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S_%f")
        if stamp_offset:
            stamp = f"{stamp}_{stamp_offset:02d}"
        directory = Path(self.migrations_path)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{stamp}_{action}_{table}.py"
        collision = 1
        while path.exists():
            path = directory / f"{stamp}_{collision:02d}_{action}_{table}.py"
            collision += 1
        path.write_text(self.render(model, previous_lines=previous_lines))
        return str(path)
