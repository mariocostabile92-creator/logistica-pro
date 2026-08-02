import os
import tempfile
from pathlib import Path
from typing import Protocol

from app.core.config import SETTINGS
from app.core.runtime_storage import atomic_write, resolve_storage_key, safe_relative_key


NAMESPACE = "attachments"


class AttachmentStorageProvider(Protocol):
    def save(self, stored_filename: str, content: bytes) -> str: ...
    def read(self, storage_path: str) -> bytes: ...
    def delete(self, storage_path: str) -> None: ...
    def resolve(self, storage_path: str) -> Path: ...


class LocalAttachmentStorage:
    def __init__(self, root: Path | None = None):
        self.root = (root or SETTINGS.runtime_storage_root / "attachments").resolve()
        self._uses_runtime_root = root is None

    def save(self, stored_filename: str, content: bytes) -> str:
        storage_key = safe_relative_key(stored_filename)
        if self._uses_runtime_root:
            atomic_write(NAMESPACE, storage_key, content)
            return storage_key
        target = self.resolve(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return storage_key

    def read(self, storage_path: str) -> bytes:
        return self.resolve(storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        target = self.resolve(storage_path)
        if target.exists():
            target.unlink()

    def resolve(self, storage_path: str) -> Path:
        storage_key = safe_relative_key(storage_path)
        if self._uses_runtime_root:
            return resolve_storage_key(NAMESPACE, storage_key)
        target = (self.root / storage_key).resolve()
        if self.root != target.parent and self.root not in target.parents:
            raise ValueError("Percorso allegato non valido.")
        return target


attachment_storage: AttachmentStorageProvider = LocalAttachmentStorage()
