from future.interfaces.IDatabase import IDatabase
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool


class SQLiteDatabase(IDatabase):
    def __init__(self, host: str = "", port: int = 0, username: str = "", password: str = "", database: str = "database"):
        super().__init__(host, port, username, password, database)
        self.client = None

    async def connect(self):
        name = self.database or ":memory:"
        if name == ":memory:":
            self.client = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
            return self.client
        path = Path(f"{name}.sqlite")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.client = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
        async with self.client.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return self.client

    async def disconnect(self):
        if self.client is not None:
            await self.client.dispose()
            self.client = None

    async def save(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        data = model.to_dict()
        col_sql = ", ".join(f'"{column}"' for column in data.keys())
        val_sql = ", ".join(f":{column}" for column in data.keys())
        upd_sql = ", ".join(f'"{column}"=excluded."{column}"' for column in data.keys() if column != "id")
        if "id" in data and upd_sql:
            insert_sql = text(f'INSERT INTO "{table}" ({col_sql}) VALUES ({val_sql}) ON CONFLICT("id") DO UPDATE SET {upd_sql}')
        else:
            insert_sql = text(f'INSERT INTO "{table}" ({col_sql}) VALUES ({val_sql})')
        async with self.client.begin() as connection:
            await connection.execute(insert_sql, data)
        return {"status": "saved", "table": table, "id": data.get("id")}

    async def find(self, model, id):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        sql = text(f'SELECT * FROM "{table}" WHERE "id" = :id LIMIT 1')
        async with self.client.connect() as connection:
            row = (await connection.execute(sql, {"id": id})).mappings().first()
        if row is None:
            return None
        return model.__class__(**dict(row))

    async def all(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        sql = text(f'SELECT * FROM "{table}"')
        async with self.client.connect() as connection:
            rows = (await connection.execute(sql)).mappings().all()
        return [model.__class__(**dict(row)) for row in rows]

    async def get(self, model, wheres, limit=None, orders=None):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        clauses = []
        params = {}
        for index, (column, operator, value) in enumerate(wheres):
            if operator == "in":
                values = list(value)
                if not values:
                    return []
                keys = []
                for item_index, item in enumerate(values):
                    key = f"v{index}_{item_index}"
                    keys.append(f":{key}")
                    params[key] = item
                clauses.append(f'"{column}" IN ({", ".join(keys)})')
                continue
            if operator == "like":
                key = f"v{index}"
                clauses.append(f'"{column}" LIKE :{key}')
                params[key] = value
                continue
            if operator not in ("=", ">", ">=", "<", "<=", "!="):
                raise ValueError(f"Unsupported operator: {operator}")
            key = f"v{index}"
            clauses.append(f'"{column}" {operator} :{key}')
            params[key] = value
        sql = f'SELECT * FROM "{table}"'
        if clauses:
            sql += f" WHERE {' AND '.join(clauses)}"
        if orders:
            sql += " ORDER BY " + ", ".join(f'"{column}" {direction}' for column, direction in orders)
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        async with self.client.connect() as connection:
            rows = (await connection.execute(text(sql), params)).mappings().all()
        return [model.__class__(**dict(row)) for row in rows]

    async def delete(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        sql = text(f'DELETE FROM "{table}" WHERE "id" = :id')
        async with self.client.begin() as connection:
            await connection.execute(sql, {"id": getattr(model, "id", None)})
        return {"status": "deleted", "table": table, "id": getattr(model, "id", None)}

    async def update(self, model, changes):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        if not changes:
            return {"status": "noop", "table": table}
        set_sql = ", ".join(f'"{column}"=:{column}' for column in changes.keys())
        params = dict(changes)
        params["id"] = getattr(model, "id", None)
        sql = text(f'UPDATE "{table}" SET {set_sql} WHERE "id" = :id')
        async with self.client.begin() as connection:
            await connection.execute(sql, params)
        return {"status": "updated", "table": table, "id": params["id"]}

    async def schema_create(self, blueprint):
        if self.client is None:
            await self.connect()
        definitions, indexes = self._schema_parts(blueprint)
        create_sql = text(f'CREATE TABLE IF NOT EXISTS "{blueprint.name}" ({", ".join(definitions)})')
        async with self.client.begin() as connection:
            await connection.execute(create_sql)
            for index_sql in indexes:
                await connection.execute(text(index_sql))
        return {"status": "created", "table": blueprint.name}

    def _schema_parts(self, blueprint, index_table=None):
        definitions = []
        indexes = []
        for column in blueprint.columns:
            if column.type == "string":
                sql_type = f"VARCHAR({column.length or 255})"
            elif column.type == "text":
                sql_type = "TEXT"
            elif column.type == "integer":
                sql_type = "INTEGER"
            elif column.type == "float":
                sql_type = "REAL"
            elif column.type == "boolean":
                sql_type = "INTEGER"
            elif column.type == "datetime":
                sql_type = "DATETIME"
            else:
                raise ValueError(f"Unsupported column type: {column.type}")
            null_sql = "NULL" if column.is_nullable else "NOT NULL"
            default_sql = ""
            if column.default_value is not None:
                if isinstance(column.default_value, str):
                    default_sql = f" DEFAULT '{column.default_value}'"
                else:
                    default_sql = f" DEFAULT {column.default_value}"
            primary_sql = " PRIMARY KEY" if column.is_primary else ""
            unique_sql = " UNIQUE" if column.is_unique and not column.is_primary else ""
            definitions.append(f'"{column.name}" {sql_type} {null_sql}{default_sql}{primary_sql}{unique_sql}')
            if column.is_index and not column.is_primary and not column.is_unique:
                table = index_table or blueprint.name
                indexes.append(f'CREATE INDEX IF NOT EXISTS "index_{table}_{column.name}" ON "{table}" ("{column.name}")')
        return definitions, indexes

    async def schema_update(self, blueprint):
        if self.client is None:
            await self.connect()
        if not await self.table_exists(blueprint.name):
            return await self.schema_create(blueprint)
        async with self.client.connect() as connection:
            rows = (await connection.execute(text(f'PRAGMA table_info("{blueprint.name}")'))).mappings().all()
        existing = {row["name"] for row in rows}
        desired = {column.name for column in blueprint.columns}
        temporary = f"_future_migrate_{blueprint.name}"
        definitions, _ = self._schema_parts(blueprint)
        _, indexes = self._schema_parts(blueprint, index_table=blueprint.name)
        async with self.client.begin() as connection:
            await connection.execute(text(f'DROP TABLE IF EXISTS "{temporary}"'))
            await connection.execute(text(f'CREATE TABLE "{temporary}" ({", ".join(definitions)})'))
            targets = []
            sources = []
            backfills = {}
            for index, column in enumerate(blueprint.columns):
                quoted = f'"{column.name}"'
                if column.name in existing:
                    source = quoted
                    if not column.is_nullable:
                        key = f"future_backfill_{index}"
                        source = f"COALESCE({quoted}, :{key})"
                        backfills[key] = column.backfill_value()
                elif not column.is_nullable:
                    key = f"future_backfill_{index}"
                    source = f":{key}"
                    backfills[key] = column.backfill_value()
                else:
                    continue
                targets.append(quoted)
                sources.append(source)
            if targets:
                await connection.execute(text(f'INSERT INTO "{temporary}" ({", ".join(targets)}) SELECT {", ".join(sources)} FROM "{blueprint.name}"'), backfills)
            await connection.execute(text(f'DROP TABLE "{blueprint.name}"'))
            await connection.execute(text(f'ALTER TABLE "{temporary}" RENAME TO "{blueprint.name}"'))
            for index_sql in indexes:
                await connection.execute(text(index_sql))
        return {"status": "updated", "table": blueprint.name, "columns": sorted(desired)}

    async def schema_drop(self, name):
        if self.client is None:
            await self.connect()
        async with self.client.begin() as connection:
            await connection.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
        return {"status": "dropped", "table": name}

    async def table_exists(self, name):
        if self.client is None:
            await self.connect()
        sql = text('SELECT 1 FROM sqlite_master WHERE type = \'table\' AND name = :name LIMIT 1')
        async with self.client.connect() as connection:
            return (await connection.execute(sql, {"name": name})).first() is not None

    async def _ensure_migrations_table(self):
        if self.client is None:
            await self.connect()
        sql = text('CREATE TABLE IF NOT EXISTS "migrations" ("name" VARCHAR(255) PRIMARY KEY, "batch" INTEGER NOT NULL)')
        async with self.client.begin() as connection:
            await connection.execute(sql)

    async def migrations_get(self):
        await self._ensure_migrations_table()
        async with self.client.connect() as connection:
            rows = (await connection.execute(text('SELECT "name" FROM "migrations" ORDER BY "batch", "name"'))).mappings().all()
        return [row["name"] for row in rows]

    async def migrations_put(self, name, batch):
        await self._ensure_migrations_table()
        sql = text('INSERT INTO "migrations" ("name", "batch") VALUES (:name, :batch)')
        async with self.client.begin() as connection:
            await connection.execute(sql, {"name": name, "batch": batch})

    async def migrations_delete(self, name):
        await self._ensure_migrations_table()
        sql = text('DELETE FROM "migrations" WHERE "name" = :name')
        async with self.client.begin() as connection:
            await connection.execute(sql, {"name": name})

    async def migrations_max_batch(self):
        await self._ensure_migrations_table()
        async with self.client.connect() as connection:
            row = (await connection.execute(text('SELECT MAX("batch") AS "batch" FROM "migrations"'))).mappings().first()
        if row is None or row["batch"] is None:
            return 0
        return int(row["batch"])

    async def migrations_batch_for(self, name):
        await self._ensure_migrations_table()
        async with self.client.connect() as connection:
            row = (await connection.execute(text('SELECT "batch" FROM "migrations" WHERE "name" = :name'), {"name": name})).mappings().first()
        if row is None:
            return None
        return int(row["batch"])
