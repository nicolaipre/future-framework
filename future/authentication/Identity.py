from __future__ import annotations

from typing import Any


class Identity:
    __slots__ = ("subject", "provider", "claims", "roles", "scopes", "_initialized")
    subject: str
    provider: str
    claims: dict[str, Any]
    roles: tuple[str, ...]
    scopes: tuple[str, ...]
    _initialized: bool

    def __init__(self, subject: str, provider: str, claims: dict[str, Any] | None = None, roles: tuple[str, ...] = (), scopes: tuple[str, ...] = ()) -> None:
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "claims", dict(claims or {}))
        object.__setattr__(self, "roles", tuple(roles))
        object.__setattr__(self, "scopes", tuple(scopes))
        object.__setattr__(self, "_initialized", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_initialized", False):
            raise AttributeError("Identity is immutable")
        object.__setattr__(self, name, value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Identity):
            return False
        return (self.subject, self.provider, self.claims, self.roles, self.scopes) == (other.subject, other.provider, other.claims, other.roles, other.scopes)

    def __repr__(self) -> str:
        return f"Identity(subject={self.subject!r}, provider={self.provider!r}, claims={self.claims!r}, roles={self.roles!r}, scopes={self.scopes!r})"
