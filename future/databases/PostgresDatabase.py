from future.interfaces.IDatabase import IDatabase
from sqlalchemy import BigInteger, String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import create_async_engine
from urllib.parse import quote_plus
from uuid import uuid4


class PostgresDatabase(IDatabase):
    def __init__(self, host: str, port: int, username: str, password: str, database: str):
        super().__init__(host, port, username, password, database)
        self.client = None

    async def connect(self):
        url = f"postgresql+asyncpg://{quote_plus(self.username)}:{quote_plus(self.password)}@{self.host}:{self.port}/{self.database}"
        self.client = create_async_engine(url)
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
        upd_sql = ", ".join(f'"{column}"=EXCLUDED."{column}"' for column in data.keys() if column != "id")
        if "id" in data and upd_sql:
            insert_sql = text(f'INSERT INTO "{table}" ({col_sql}) VALUES ({val_sql}) ON CONFLICT ("id") DO UPDATE SET {upd_sql}')
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
        array_binds = {}
        for index, (column, operator, value) in enumerate(wheres):
            if operator == "in":
                values = list(value)
                if not values:
                    return []
                # One array bind avoids Postgres' ~32767 bind-variable limit.
                key = f"v{index}"
                clauses.append(f'"{column}" = ANY(:{key})')
                params[key] = values
                sample = values[0]
                if isinstance(sample, int) and not isinstance(sample, bool):
                    array_binds[key] = ARRAY(BigInteger)
                else:
                    array_binds[key] = ARRAY(String)
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
        stmt = text(sql)
        for key, array_type in array_binds.items():
            stmt = stmt.bindparams(bindparam(key, type_=array_type))
        async with self.client.connect() as connection:
            rows = (await connection.execute(stmt, params)).mappings().all()
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
        parts, indexes = self._schema_parts(blueprint)
        create_sql = text(f"CREATE TABLE IF NOT EXISTS \"{blueprint.name}\" ({', '.join(parts)})")
        async with self.client.begin() as connection:
            await connection.execute(create_sql)
            for index_name in indexes:
                await connection.execute(text(f"CREATE INDEX IF NOT EXISTS \"index_{blueprint.name}_{index_name}\" ON \"{blueprint.name}\" (\"{index_name}\")"))
        return {"status": "created", "table": blueprint.name}

    def _schema_parts(self, blueprint):
        definitions = []
        uniques = []
        indexes = []
        for column in blueprint.columns:
            if column.type == "string":
                sql_type = f"VARCHAR({column.length or 255})"
            elif column.type == "text":
                sql_type = "TEXT"
            elif column.type == "integer":
                sql_type = "BIGINT"
            elif column.type == "float":
                sql_type = "DOUBLE PRECISION"
            elif column.type == "boolean":
                sql_type = "BOOLEAN"
            elif column.type == "datetime":
                sql_type = "TIMESTAMP"
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
            definitions.append(f"\"{column.name}\" {sql_type} {null_sql}{default_sql}{primary_sql}")
            if column.is_unique and not column.is_primary:
                uniques.append(f"UNIQUE (\"{column.name}\")")
            if column.is_index and not column.is_primary and not column.is_unique:
                indexes.append(column.name)
        return definitions + uniques, indexes

    async def schema_update(self, blueprint):
        if self.client is None:
            await self.connect()
        if not await self.table_exists(blueprint.name):
            return await self.schema_create(blueprint)
        sql = text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table ORDER BY ordinal_position")
        async with self.client.connect() as connection:
            rows = (await connection.execute(sql, {"table": blueprint.name})).mappings().all()
        existing = {row["column_name"] for row in rows}
        common = [column.name for column in blueprint.columns if column.name in existing]
        temporary = f"_future_{uuid4().hex[:8]}_{blueprint.name}"[:63]
        parts, indexes = self._schema_parts(blueprint)
        async with self.client.begin() as connection:
            await connection.execute(text(f'DROP TABLE IF EXISTS "{temporary}"'))
            await connection.execute(text(f'CREATE TABLE "{temporary}" ({", ".join(parts)})'))
            if common:
                columns = ", ".join(f'"{name}"' for name in common)
                await connection.execute(text(f'INSERT INTO "{temporary}" ({columns}) SELECT {columns} FROM "{blueprint.name}"'))
            await connection.execute(text(f'DROP TABLE "{blueprint.name}"'))
            await connection.execute(text(f'ALTER TABLE "{temporary}" RENAME TO "{blueprint.name}"'))
            for index_name in indexes:
                await connection.execute(text(f"CREATE INDEX IF NOT EXISTS \"index_{blueprint.name}_{index_name}\" ON \"{blueprint.name}\" (\"{index_name}\")"))
        return {"status": "updated", "table": blueprint.name, "columns": sorted(column.name for column in blueprint.columns)}

    async def schema_drop(self, name):
        if self.client is None:
            await self.connect()
        async with self.client.begin() as connection:
            await connection.execute(text(f"DROP TABLE IF EXISTS \"{name}\""))
        return {"status": "dropped", "table": name}

    async def table_exists(self, name):
        if self.client is None:
            await self.connect()
        sql = text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :name LIMIT 1")
        async with self.client.connect() as connection:
            return (await connection.execute(sql, {"name": name})).first() is not None

    async def _ensure_migrations_table(self):
        if self.client is None:
            await self.connect()
        sql = text("CREATE TABLE IF NOT EXISTS \"migrations\" (\"name\" VARCHAR(255) PRIMARY KEY, \"batch\" INT NOT NULL)")
        async with self.client.begin() as connection:
            await connection.execute(sql)

    async def migrations_get(self):
        await self._ensure_migrations_table()
        async with self.client.connect() as connection:
            rows = (await connection.execute(text("SELECT \"name\" FROM \"migrations\" ORDER BY \"batch\", \"name\""))).mappings().all()
        return [row["name"] for row in rows]

    async def migrations_put(self, name, batch):
        await self._ensure_migrations_table()
        sql = text("INSERT INTO \"migrations\" (\"name\", \"batch\") VALUES (:name, :batch) ON CONFLICT (\"name\") DO UPDATE SET \"batch\" = EXCLUDED.\"batch\"")
        async with self.client.begin() as connection:
            await connection.execute(sql, {"name": name, "batch": batch})

    async def migrations_delete(self, name):
        await self._ensure_migrations_table()
        sql = text("DELETE FROM \"migrations\" WHERE \"name\" = :name")
        async with self.client.begin() as connection:
            await connection.execute(sql, {"name": name})

    async def migrations_max_batch(self):
        await self._ensure_migrations_table()
        async with self.client.connect() as connection:
            row = (await connection.execute(text("SELECT MAX(\"batch\") AS batch FROM \"migrations\""))).mappings().first()
        if row is None or row["batch"] is None:
            return 0
        return int(row["batch"])

    async def migrations_batch_for(self, name):
        await self._ensure_migrations_table()
        async with self.client.connect() as connection:
            row = (await connection.execute(text("SELECT \"batch\" FROM \"migrations\" WHERE \"name\" = :name"), {"name": name})).mappings().first()
        if row is None:
            return None
        return int(row["batch"])
