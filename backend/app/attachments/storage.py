from pathlib import Path
from typing import Protocol

from app.core.config import SETTINGS


class AttachmentStorageProvider(Protocol):
    def save(self, stored_filename: str, content: bytes) -> str: ...
    def read(self, storage_path: str) -> bytes: ...
    def delete(self, storage_path: str) -> None: ...
    def resolve(self, storage_path: str) -> Path: ...


class LocalAttachmentStorage:
    def __init__(self, root: Path | None = None):
        self.root = (root or SETTINGS.runtime_storage_root / "attachments").resolve()

    def save(self, stored_filename: str, content: bytes) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        target = (self.root / stored_filename).resolve()
        if target.parent != self.root:
            raise ValueError("Percorso allegato non valido.")
        target.write_bytes(content)
        return stored_filename

    def read(self, storage_path: str) -> bytes:
        return self.resolve(storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        target = self.resolve(storage_path)
        if target.exists():
            target.unlink()

    def resolve(self, storage_path: str) -> Path:
        target = (self.root / storage_path).resolve()
        if target.parent != self.root:
            raise ValueError("Percorso allegato non valido.")
        return target


attachment_storage: AttachmentStorageProvider = LocalAttachmentStorage()
