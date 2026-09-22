from unittest.mock import AsyncMock, MagicMock, patch

from future.databases.ElasticsearchDatabase import ElasticsearchDatabase
from future.interfaces.IModel import IModel
from future.migrations import Blueprint


class Doc(IModel):
    __table__ = "docs"


def _es():
    es = ElasticsearchDatabase(host="https://localhost:9200", port=9200, username="u", password="p")
    es.client = MagicMock()
    es.client.get = AsyncMock()
    es.client.search = AsyncMock()
    es.client.index = AsyncMock()
    return es


async def test_elasticsearch_find_and_all():
    es = _es()
    es.client.get.return_value = {"_source": {"id": "1", "title": "hi"}}
    es.client.search.return_value = {"hits": {"hits": [{"_source": {"id": "1", "title": "hi"}}, {"_source": {"id": "2", "title": "yo"}}]}}

    found = await es.find(Doc(), "1")
    assert found is not None and found.title == "hi"
    es.client.get.assert_called_with(index="docs", id="1")

    rows = await es.all(Doc())
    assert len(rows) == 2
    assert rows[1].id == "2"


async def test_elasticsearch_get_builds_bool_query():
    es = _es()
    es.client.search.return_value = {"hits": {"hits": [{"_source": {"id": "9", "price": 5}}]}}

    rows = await es.get(Doc(), wheres=[("price", ">", 1)], limit=5, orders=[("price", "asc")])
    assert len(rows) == 1
    body = es.client.search.call_args.kwargs["body"]
    assert body["size"] == 5
    assert {"range": {"price": {"gt": 1}}} in body["query"]["bool"]["must"]
    assert body["sort"] == [{"price": {"order": "asc"}}]


async def test_elasticsearch_connect_builds_url():
    with patch("future.databases.ElasticsearchDatabase.AsyncElasticsearch") as client_cls:
        es = ElasticsearchDatabase(host="localhost", port=9200, username="u", password="p")
        await es.connect()
        client_cls.assert_called_with("http://localhost:9200", basic_auth=("u", "p"))
    with patch("future.databases.ElasticsearchDatabase.AsyncElasticsearch") as client_cls:
        es = ElasticsearchDatabase(host="http://127.0.0.1:9200", port=9200, username="elastic", password="password")
        await es.connect()
        client_cls.assert_called_with("http://127.0.0.1:9200", basic_auth=("elastic", "password"))


async def test_elasticsearch_save_indexes_document():
    es = _es()
    es.client.index.return_value = {"result": "created"}
    result = await es.save(Doc(id="1", title="x"))
    assert result["result"]["result"] == "created"
    es.client.index.assert_called_with(index="docs", id="1", document={"id": "1", "title": "x"}, refresh=True)


async def test_elasticsearch_schema_update_extends_mapping():
    es = _es()
    es.client.indices = MagicMock()
    es.client.indices.exists = AsyncMock(return_value=True)
    es.client.indices.get_mapping = AsyncMock(return_value={"docs": {"mappings": {"properties": {"id": {"type": "keyword"}}}}})
    es.client.indices.put_mapping = AsyncMock()
    blueprint = Blueprint("docs", "default", action="update")
    blueprint.id()
    blueprint.string("title")

    result = await es.schema_update(blueprint)

    assert result["status"] == "updated"
    properties = es.client.indices.put_mapping.call_args.kwargs["properties"]
    assert properties["id"]["type"] == "keyword"
    assert properties["title"]["type"] == "text"
