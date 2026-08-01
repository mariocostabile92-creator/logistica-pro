from pathlib import Path
from typing import Protocol

from app.core.runtime_storage import (
    atomic_write,
    resolve_storage_key,
    safe_relative_key,
)


NAMESPACE = "journal_media"


class MediaStorage(Protocol):
    def save(self, storage_key: str, data: bytes) -> str: ...
    def delete(self, storage_key: str) -> None: ...
    def path(self, storage_key: str) -> Path: ...
    def keys(self) -> set[str]: ...


class PrivateLocalMediaStorage:
    def save(self, storage_key: str, data: bytes) -> str:
        key = safe_relative_key(storage_key)
        atomic_write(NAMESPACE, key, data)
        return key

    def delete(self, storage_key: str) -> None:
        self.path(storage_key).unlink(missing_ok=True)

    def path(self, storage_key: str) -> Path:
        return resolve_storage_key(NAMESPACE, storage_key)

    def keys(self) -> set[str]:
        root = resolve_storage_key(NAMESPACE, "__probe__").parent
        if not root.exists():
            return set()
        return {
            item.relative_to(root).as_posix()
            for item in root.rglob("*")
            if item.is_file() and not item.name.endswith(".tmp")
        }


media_storage: MediaStorage = PrivateLocalMediaStorage()
