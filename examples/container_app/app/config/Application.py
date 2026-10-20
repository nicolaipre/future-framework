from examples.container_app.app.authentication.TestAuthentication import TestAuthentication
from examples.container_app.app.interfaces.IUserRepository import IUserRepository
from examples.container_app.app.repositories.MemoryUserRepository import MemoryUserRepository


CONFIG = {
    "APP_NAME": "Future container example",
    "APP_DOMAIN": "",
    "APP_DEBUG": False,
    "BINDINGS": {
        IUserRepository: MemoryUserRepository,
    },
    "AUTHENTICATION": {
        "default": "basic",
        "providers": {
            "basic": {
                "driver": TestAuthentication,
            },
        },
    },
    "OPENAPI": {
        "enabled": False,
        "auto_routes": False,
    },
}
