import logging

from datetime import datetime, timezone

from future.application import Future
from future.lifespan import Lifespan
from future.logger import ACCESS_LOG_FORMAT, DEFAULT_LOG_FORMAT, ColoredFormatter, UvicornAccessFormatter, UvicornDefaultFormatter, create_uvicorn_logging_config


def _record(name: str, message: str, args: tuple = (), level: int = logging.INFO) -> logging.LogRecord:
    record = logging.LogRecord(name, level, "", 0, message, args, None)
    record.created = datetime(2026, 9, 26, 7, 2, 10, 549647, tzinfo=timezone.utc).timestamp()
    return record


def test_future_formatter_includes_utc_timestamp():
    formatter = ColoredFormatter(DEFAULT_LOG_FORMAT, use_colors=True)
    output = formatter.format(_record("future", "refreshed %d users", (929,)))
    assert output == "2026-09-26T07:02:10.549Z \033[32mINFO\033[0m:     refreshed 929 users"


def test_future_and_uvicorn_use_the_same_level_colors():
    future_formatter = ColoredFormatter(DEFAULT_LOG_FORMAT, use_colors=True)
    uvicorn_formatter = UvicornDefaultFormatter(DEFAULT_LOG_FORMAT, use_colors=True)
    colors = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[38;5;208m",
        logging.ERROR: "\033[31m",
    }

    for level, color in colors.items():
        record = _record("test", "message", level=level)
        future_output = future_formatter.format(record)
        uvicorn_output = uvicorn_formatter.format(record)
        assert future_output == uvicorn_output
        assert f"{color}{logging.getLevelName(level)}\033[0m" in future_output


def test_uvicorn_access_formatter_uses_lighter_http_status_colors():
    formatter = UvicornAccessFormatter(ACCESS_LOG_FORMAT, use_colors=True)
    colors = {200: "\033[97m", 302: "\033[92m", 404: "\033[91m", 500: "\033[94m"}

    for status, color in colors.items():
        record = _record("uvicorn.access", '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:54506", "GET", "/health", "1.1", status))
        output = formatter.format(record)
        assert output.startswith("2026-09-26T07:02:10.549Z \033[32mINFO\033[0m:     127.0.0.1:54506")
        assert color in output


def test_uvicorn_logging_config_uses_timestamp_formatters():
    config = create_uvicorn_logging_config()
    assert config["formatters"]["default"]["()"] is UvicornDefaultFormatter
    assert config["formatters"]["access"]["()"] is UvicornAccessFormatter
    assert config["formatters"]["default"]["use_colors"] is True
    assert config["formatters"]["access"]["use_colors"] is True


def test_future_run_passes_timestamp_logging_config_to_uvicorn(monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("future.application.uvicorn.run", fake_run)
    app = Future(lifespan=Lifespan(), config={"APP_NAME": "test", "APP_DOMAIN": "example.com", "APP_DEBUG": False})
    app.run(workers=1)

    assert captured["log_config"]["formatters"]["default"]["()"] is UvicornDefaultFormatter
    assert captured["log_config"]["formatters"]["access"]["()"] is UvicornAccessFormatter
