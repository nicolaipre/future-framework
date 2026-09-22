from future.database import Database
from future.interfaces.IDatabase import IDatabase
from future.interfaces.IModel import IModel, Query
import re


class FakeDatabase(IDatabase):
    def __init__(self):
        super().__init__(host="x", port=0, username="", password="", database="")
        self.rows = {}

    async def connect(self):
        return self

    async def disconnect(self):
        pass

    async def save(self, model):
        data = model.to_dict()
        table = model.tableize()
        self.rows.setdefault(table, {})
        self.rows[table][str(data["id"])] = data
        return {"status": "saved", "id": data["id"]}

    async def find(self, model, id):
        table = model.tableize()
        data = self.rows.get(table, {}).get(str(id))
        if data is None:
            return None
        return model.__class__(**data)

    async def all(self, model):
        table = model.tableize()
        return [model.__class__(**row) for row in self.rows.get(table, {}).values()]

    async def get(self, model, wheres, limit=None, orders=None):
        rows = await self.all(model)
        for column, operator, value in wheres:
            if operator == "=":
                rows = [row for row in rows if getattr(row, column) == value]
            elif operator == ">":
                rows = [row for row in rows if getattr(row, column) > value]
            elif operator == "like":
                filtered = []
                for row in rows:
                    current = getattr(row, column, None)
                    if current is None:
                        continue
                    parts = []
                    for char in str(value):
                        if char == "%":
                            parts.append(".*")
                        elif char == "_":
                            parts.append(".")
                        else:
                            parts.append(re.escape(char))
                    if re.search("^" + "".join(parts) + "$", str(current)):
                        filtered.append(row)
                rows = filtered
            else:
                raise ValueError(operator)
        if orders:
            for column, direction in reversed(orders):
                rows.sort(key=lambda row: getattr(row, column), reverse=direction == "desc")
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def delete(self, model):
        table = model.tableize()
        self.rows.get(table, {}).pop(str(getattr(model, "id")), None)
        return {"status": "deleted"}

    async def update(self, model, changes):
        table = model.tableize()
        row = self.rows.get(table, {}).get(str(getattr(model, "id")))
        if row is not None:
            row.update(changes)
        return {"status": "updated"}

    async def schema_create(self, blueprint):
        pass

    async def schema_update(self, blueprint):
        pass

    async def schema_drop(self, name):
        pass

    async def migrations_get(self):
        return []

    async def migrations_put(self, name, batch):
        pass

    async def migrations_delete(self, name):
        pass

    async def migrations_max_batch(self):
        return 0

    async def migrations_batch_for(self, name):
        return 0


class Item(IModel):
    __table__ = "items"
    __connection__ = "fake"


def setup_module():
    Database().set_connection_details({"default": "fake", "fake": FakeDatabase()})


async def test_model_save_find_all():
    setup_module()
    Database()._connections["fake"].rows = {}
    item = Item(id="1", name="a", price=10)
    await item.save()
    found = await Item.find("1")
    assert found is not None
    assert found.name == "a"
    assert len(await Item.all()) == 1


async def test_model_where_and_order():
    setup_module()
    db = Database()._connections["fake"]
    db.rows = {}
    await Item(id="1", name="a", price=10).save()
    await Item(id="2", name="b", price=20).save()
    await Item(id="3", name="c", price=30).save()
    rows = await Item.where("price", ">", 10).order_by("price", "desc").get()
    assert [row.id for row in rows] == ["3", "2"]
    first = await Item.where("name", "b").first()
    assert first is not None and first.id == "2"


async def test_model_where_limit():
    setup_module()
    db = Database()._connections["fake"]
    db.rows = {}
    await Item(id="1", name="a", price=10).save()
    await Item(id="2", name="b", price=20).save()
    await Item(id="3", name="c", price=30).save()
    rows = await Item.where("price", ">", 10).order_by("price", "desc").limit(1).get()
    assert [row.id for row in rows] == ["3"]


async def test_model_update_and_delete():
    setup_module()
    Database()._connections["fake"].rows = {}
    item = Item(id="1", name="a", price=10)
    await item.save()
    await item.update(name="b", price=20)
    found = await Item.find("1")
    assert found.name == "b" and found.price == 20
    await found.delete()
    assert await Item.find("1") is None
    assert await Item.all() == []


def test_query_requires_get_or_first():
    q = Query(Item())
    assert "Query" in repr(q)
    try:
        len(q)
        assert False
    except TypeError as exc:
        assert "len" in str(exc)
    try:
        list(q)
        assert False
    except TypeError as exc:
        assert "iterable" in str(exc)


def test_to_dict_skips_imodel_relations():
    from future.models.PostModel import PostModel
    from future.models.UserModel import UserModel
    post = PostModel(id="101", title="t", content="c", author_id="1", author=UserModel(id="1", name="Ada", email="ada@example.com"))
    data = post.to_dict()
    assert data["id"] == "101"
    assert data["author_id"] == "1"
    assert "author" not in data


def test_model_openapi_schema_includes_fields():
    from future.models.UserModel import UserModel
    schema = UserModel(id="1", name="Ada", email="ada@example.com").openapi_schema()
    assert schema["type"] == "object"
    assert "email" in schema["properties"]
    assert schema["properties"]["id"]["type"] == "string"


async def test_model_where_like_and_to_json():
    setup_module()
    Database()._connections["fake"].rows = {}
    await Item(id="1", name="apple", price=1).save()
    await Item(id="2", name="pear", price=2).save()
    rows = await Item.where("name", "like", "%ppl%").get()
    assert [row.id for row in rows] == ["1"]
    item = await Item.find("1")
    assert '"name": "apple"' in item.to_json()
    assert Item().tableize() == "items"


async def test_model_find_missing_and_first_empty():
    setup_module()
    Database()._connections["fake"].rows = {}
    assert await Item.find("nope") is None
    assert await Item.where("name", "ghost").first() is None
    assert await Item.all() == []
