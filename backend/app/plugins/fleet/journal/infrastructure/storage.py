from pathlib import Path
from typing import Protocol

from app.core.config import DATA_DIR


class MediaStorage(Protocol):
    def save(self, session_id: str, media_id: str, data: bytes) -> str: ...
    def delete(self, storage_key: str) -> None: ...
    def path(self, storage_key: str) -> Path: ...


class PrivateLocalMediaStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, session_id: str, media_id: str, data: bytes) -> str:
        folder = self.root / session_id
        folder.mkdir(parents=True, exist_ok=True)
        key = f"{session_id}/{media_id}.bin"
        (self.root / key).write_bytes(data)
        return key

    def delete(self, storage_key: str) -> None:
        target = self.path(storage_key)
        if self.root.resolve() not in target.parents:
            return
        target.unlink(missing_ok=True)

    def path(self, storage_key: str) -> Path:
        target = (self.root / storage_key).resolve()
        if self.root.resolve() not in target.parents:
            return self.root / "__invalid__"
        return target


media_storage: MediaStorage = PrivateLocalMediaStorage(
    DATA_DIR / "journal_media"
)
