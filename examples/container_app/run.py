from future.application import Future

from examples.container_app.app.config.Application import CONFIG
from examples.container_app.app.routes import routes


def create_app() -> Future:
    application = Future(config=CONFIG)
    application.add_routes(routes)
    return application


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=1)
