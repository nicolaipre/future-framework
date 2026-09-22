from future.interfaces.IDatabase import IDatabase


class ClickhouseDatabase(IDatabase):
    def __init__(self, host: str, port: int, username: str, password: str, database: str):
        super().__init__(host, port, username, password, database)
        self.client = None

    async def connect(self):
        from asynch import Connection
        self.client = Connection(host=self.host, port=self.port, user=self.username, password=self.password, database=self.database)
        await self.client.connect()
        return self.client

    async def disconnect(self):
        if self.client is not None:
            await self.client.close()
            self.client = None

    async def save(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        data = model.to_dict()
        doc_id = data.get("id")
        async with self.client.cursor() as cursor:
            if doc_id is not None:
                await cursor.execute(f"ALTER TABLE `{table}` DELETE WHERE id = %(id)s", {"id": doc_id})
            columns = list(data.keys())
            col_sql = ", ".join(f"`{column}`" for column in columns)
            await cursor.execute(f"INSERT INTO `{table}` ({col_sql}) VALUES", [tuple(data[column] for column in columns)])
        return {"status": "saved", "table": table, "id": doc_id}

    async def find(self, model, id):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        async with self.client.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM `{table}` WHERE id = %(id)s LIMIT 1", {"id": id})
            rows = await cursor.fetchall()
            names = [column[0] for column in cursor.description]
        if not rows:
            return None
        return model.__class__(**dict(zip(names, rows[0], strict=True)))

    async def all(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        async with self.client.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM `{table}`")
            rows = await cursor.fetchall()
            names = [column[0] for column in cursor.description]
        return [model.__class__(**dict(zip(names, row, strict=True))) for row in rows]

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
                    keys.append(f"%({key})s")
                    params[key] = item
                clauses.append(f"`{column}` IN ({', '.join(keys)})")
                continue
            if operator == "like":
                key = f"v{index}"
                clauses.append(f"`{column}` LIKE %({key})s")
                params[key] = value
                continue
            if operator not in ("=", ">", ">=", "<", "<=", "!="):
                raise ValueError(f"Unsupported operator: {operator}")
            key = f"v{index}"
            clauses.append(f"`{column}` {operator} %({key})s")
            params[key] = value
        sql = f"SELECT * FROM `{table}`"
        if clauses:
            sql += f" WHERE {' AND '.join(clauses)}"
        if orders:
            sql += " ORDER BY " + ", ".join(f"`{column}` {direction}" for column, direction in orders)
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        async with self.client.cursor() as cursor:
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
            names = [column[0] for column in cursor.description]
        return [model.__class__(**dict(zip(names, row, strict=True))) for row in rows]

    async def delete(self, model):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        doc_id = getattr(model, "id", None)
        async with self.client.cursor() as cursor:
            await cursor.execute(f"ALTER TABLE `{table}` DELETE WHERE id = %(id)s", {"id": doc_id})
        return {"status": "deleted", "table": table, "id": doc_id}

    async def update(self, model, changes):
        if self.client is None:
            await self.connect()
        table = model.tableize()
        doc_id = getattr(model, "id", None)
        if not changes:
            return {"status": "noop", "table": table, "id": doc_id}
        set_sql = ", ".join(f"`{column}` = %({column})s" for column in changes.keys())
        params = dict(changes)
        params["id"] = doc_id
        async with self.client.cursor() as cursor:
            await cursor.execute(f"ALTER TABLE `{table}` UPDATE {set_sql} WHERE id = %(id)s", params)
        return {"status": "updated", "table": table, "id": doc_id}

    async def schema_create(self, blueprint):
        if self.client is None:
            await self.connect()
        definitions = []
        order_by = "tuple()"
        for column in blueprint.columns:
            definitions.append(self._column_definition(column))
            if column.is_primary:
                order_by = f"`{column.name}`"
        create_sql = f"CREATE TABLE IF NOT EXISTS `{blueprint.name}` ({', '.join(definitions)}) ENGINE = MergeTree() ORDER BY {order_by}"
        async with self.client.cursor() as cursor:
            await cursor.execute(create_sql)
        return {"status": "created", "table": blueprint.name}

    def _column_type(self, column):
        if column.type in ("string", "text"):
            ch_type = "String"
        elif column.type == "integer":
            ch_type = "Int64"
        elif column.type == "float":
            ch_type = "Float64"
        elif column.type == "boolean":
            ch_type = "UInt8"
        elif column.type == "datetime":
            ch_type = "DateTime"
        else:
            raise ValueError(f"Unsupported column type: {column.type}")
        return f"Nullable({ch_type})" if column.is_nullable else ch_type

    def _column_definition(self, column):
        default = f" DEFAULT {column.default_value!r}" if column.default_value is not None else ""
        return f"`{column.name}` {self._column_type(column)}{default}"

    async def table_exists(self, name):
        if self.client is None:
            await self.connect()
        async with self.client.cursor() as cursor:
            await cursor.execute("SELECT count() FROM system.tables WHERE database = currentDatabase() AND name = %(name)s", {"name": name})
            rows = await cursor.fetchall()
        return bool(rows and rows[0][0])

    async def schema_update(self, blueprint):
        if self.client is None:
            await self.connect()
        if not await self.table_exists(blueprint.name):
            return await self.schema_create(blueprint)
        async with self.client.cursor() as cursor:
            await cursor.execute("SELECT name, type FROM system.columns WHERE database = currentDatabase() AND table = %(table)s", {"table": blueprint.name})
            rows = await cursor.fetchall()
            existing = {row[0]: row[1] for row in rows}
            desired = {column.name: column for column in blueprint.columns}
            for name, column in desired.items():
                definition = self._column_definition(column)
                if name not in existing:
                    await cursor.execute(f"ALTER TABLE `{blueprint.name}` ADD COLUMN {definition}")
                elif existing[name] != self._column_type(column):
                    await cursor.execute(f"ALTER TABLE `{blueprint.name}` MODIFY COLUMN {definition}")
            for name in existing.keys() - desired.keys():
                await cursor.execute(f"ALTER TABLE `{blueprint.name}` DROP COLUMN `{name}`")
        return {"status": "updated", "table": blueprint.name, "columns": sorted(desired)}

    async def schema_drop(self, name):
        if self.client is None:
            await self.connect()
        async with self.client.cursor() as cursor:
            await cursor.execute(f"DROP TABLE IF EXISTS `{name}`")
        return {"status": "dropped", "table": name}

    async def migrations_get(self):
        if self.client is None:
            await self.connect()
        async with self.client.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS `migrations` (`name` String, `batch` Int32) ENGINE = MergeTree() ORDER BY (`batch`, `name`)")
            await cursor.execute("SELECT name FROM migrations ORDER BY batch, name")
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def migrations_put(self, name, batch):
        if self.client is None:
            await self.connect()
        async with self.client.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS `migrations` (`name` String, `batch` Int32) ENGINE = MergeTree() ORDER BY (`batch`, `name`)")
            await cursor.execute("INSERT INTO migrations (name, batch) VALUES", [(name, batch)])

    async def migrations_delete(self, name):
        if self.client is None:
            await self.connect()
        async with self.client.cursor() as cursor:
            await cursor.execute("ALTER TABLE migrations DELETE WHERE name = %(name)s", {"name": name})

    async def migrations_max_batch(self):
        if self.client is None:
            await self.connect()
        async with self.client.cursor() as cursor:
            await cursor.execute("CREATE TABLE IF NOT EXISTS `migrations` (`name` String, `batch` Int32) ENGINE = MergeTree() ORDER BY (`batch`, `name`)")
            await cursor.execute("SELECT max(batch) FROM migrations")
            rows = await cursor.fetchall()
        if not rows or rows[0][0] is None:
            return 0
        return int(rows[0][0])

    async def migrations_batch_for(self, name):
        if self.client is None:
            await self.connect()
        async with self.client.cursor() as cursor:
            await cursor.execute("SELECT batch FROM migrations WHERE name = %(name)s", {"name": name})
            rows = await cursor.fetchall()
        if not rows:
            return None
        return int(rows[0][0])
