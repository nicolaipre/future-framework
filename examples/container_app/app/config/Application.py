from future.authentication.BasicAuthentication import BasicAuthentication

from examples.container_app.app.authentication.TestCredentials import verify_credentials
from examples.container_app.app.repositories.IUserRepository import IUserRepository
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
                "driver": BasicAuthentication,
                "options": {
                    "verify_credentials": verify_credentials,
                    "realm": "Future container example",
                },
            },
        },
    },
    "OPENAPI": {
        "enabled": False,
        "auto_routes": False,
    },
}
