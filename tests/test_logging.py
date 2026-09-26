import logging

from datetime import datetime, timezone

from future.application import Future
from future.lifespan import Lifespan
from future.logger import ColoredFormatter, UvicornAccessFormatter, UvicornDefaultFormatter, create_uvicorn_logging_config


def _record(name: str, message: str, args: tuple = ()) -> logging.LogRecord:
    record = logging.LogRecord(name, logging.INFO, "", 0, message, args, None)
    record.created = datetime(2026, 9, 26, 7, 2, 10, 549647, tzinfo=timezone.utc).timestamp()
    return record


def test_future_formatter_includes_utc_timestamp():
    formatter = ColoredFormatter("%(message)s")
    output = formatter.format(_record("future", "refreshed %d users", (929,)))
    assert output == "2026-09-26T07:02:10.549Z \033[32mINFO\033[0m:     refreshed 929 users"


def test_uvicorn_default_formatter_includes_utc_timestamp():
    formatter = UvicornDefaultFormatter("%(asctime)s %(levelprefix)s %(message)s", use_colors=False)
    output = formatter.format(_record("uvicorn.error", "Application startup complete."))
    assert output == "2026-09-26T07:02:10.549Z INFO:     Application startup complete."


def test_uvicorn_access_formatter_includes_utc_timestamp():
    formatter = UvicornAccessFormatter('%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False)
    record = _record("uvicorn.access", '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:54506", "GET", "/health", "1.1", 200))
    output = formatter.format(record)
    assert output == '2026-09-26T07:02:10.549Z INFO:     127.0.0.1:54506 - "GET /health HTTP/1.1" 200 OK'


def test_uvicorn_logging_config_uses_timestamp_formatters():
    config = create_uvicorn_logging_config()
    assert config["formatters"]["default"]["()"] is UvicornDefaultFormatter
    assert config["formatters"]["access"]["()"] is UvicornAccessFormatter


def test_future_run_passes_timestamp_logging_config_to_uvicorn(monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("future.application.uvicorn.run", fake_run)
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "test", "APP_DOMAIN": "example.com", "APP_DEBUG": False})
    app.run(workers=1)

    assert captured["log_config"]["formatters"]["default"]["()"] is UvicornDefaultFormatter
    assert captured["log_config"]["formatters"]["access"]["()"] is UvicornAccessFormatter
