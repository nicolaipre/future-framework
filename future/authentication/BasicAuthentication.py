"""HTTP Basic authentication backed by an application credential verifier."""

import base64
import binascii
import inspect

from collections.abc import Callable
from typing import Any

from future.authentication.Identity import Identity
from future.interfaces.IAuthentication import IAuthentication
from future.request import Request


class BasicAuthentication(IAuthentication):
    auth_type = "basic"

    def __init__(self, verify_credentials: Callable[[str, str], Any], realm: str = "Future") -> None:
        self.verify_credentials = verify_credentials
        self.challenge = f'Basic realm="{realm}"'

    async def authenticate(self, request: Request) -> Identity | None:
        authorization = request.headers.get("authorization", "")
        scheme, _, encoded = authorization.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return None
        try:
            username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return None
        result = self.verify_credentials(username, password)
        if inspect.isawaitable(result):
            result = await result
        if result is None or result is False:
            return None
        if isinstance(result, Identity):
            return result
        if result is True:
            return Identity(subject=username, provider="basic")
        if isinstance(result, str):
            return Identity(subject=result, provider="basic")
        if isinstance(result, dict):
            claims = dict(result.get("claims") or {})
            subject = str(result.get("subject") or result.get("id") or username)
            roles = tuple(str(role) for role in result.get("roles", ()))
            scopes = tuple(str(scope) for scope in result.get("scopes", ()))
            return Identity(subject=subject, provider="basic", claims=claims, roles=roles, scopes=scopes)
        raise TypeError(f"Basic credential verifier must return Identity, dict, str, bool, or None, got {type(result).__name__}")
