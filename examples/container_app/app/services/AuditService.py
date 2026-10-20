class AuditService:
    def describe(self, method: str, path: str) -> str:
        return f"{method} {path}"
