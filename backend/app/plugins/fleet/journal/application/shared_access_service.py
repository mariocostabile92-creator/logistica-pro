import secrets
import uuid
from datetime import datetime, timezone

from app.plugins.fleet.journal.infrastructure import shared_access_repository


class SharedAccessError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _present(item: dict) -> dict:
    return {
        "id": item["id"],
        "token": item["token"],
        "status": item["status"],
        "created_at": item["created_at"],
        "revoked_at": item.get("revoked_at"),
        "last_used_at": item.get("last_used_at"),
        "link_path": f"/app/journal/access/{item['token']}",
    }


def get_active() -> dict | None:
    item = shared_access_repository.active()
    return _present(item) if item else None


def create(regenerate: bool = False) -> dict:
    current = shared_access_repository.active()
    if current and not regenerate:
        return _present(current)
    if current:
        shared_access_repository.revoke(current["id"], _now())
    created = shared_access_repository.create({
        "id": str(uuid.uuid4()),
        "token": secrets.token_urlsafe(32),
        "created_at": _now(),
    })
    return _present(created)


def revoke(access_id: str) -> dict:
    item = shared_access_repository.revoke(access_id, _now())
    if not item:
        raise SharedAccessError("Link condiviso non trovato.", 404)
    return _present(item)


def validate(token: str, *, touch: bool = True) -> dict:
    item = shared_access_repository.get_by_token(token)
    if not item or item["status"] != "active":
        raise SharedAccessError("Link condiviso non valido o revocato.", 404)
    if touch:
        item = shared_access_repository.touch(token, _now()) or item
    return {
        "id": item["id"],
        "status": item["status"],
        "created_at": item["created_at"],
        "last_used_at": item.get("last_used_at"),
    }

