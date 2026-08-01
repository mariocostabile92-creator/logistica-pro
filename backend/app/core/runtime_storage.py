import os
import tempfile
from pathlib import Path, PurePosixPath

from app.core.config import SETTINGS


class RuntimeStorageError(RuntimeError):
    pass


def storage_root() -> Path:
    return SETTINGS.runtime_storage_root


def initialize_runtime_storage() -> Path:
    if SETTINGS.require_persistent_storage and not os.getenv("RUNTIME_STORAGE_ROOT"):
        raise RuntimeStorageError(
            "RUNTIME_STORAGE_ROOT e obbligatoria quando REQUIRE_PERSISTENT_STORAGE=true."
        )
    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        descriptor, probe = tempfile.mkstemp(prefix=".storage-probe-", dir=root)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(b"ok")
            handle.flush()
            os.fsync(handle.fileno())
        Path(probe).unlink()
    except OSError as exc:
        raise RuntimeStorageError("La root storage runtime non e scrivibile.") from exc
    return root


def safe_relative_key(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    key = PurePosixPath(normalized)
    if (
        not normalized
        or key.is_absolute()
        or any(part in {"", ".", ".."} for part in key.parts)
        or ":" in normalized
    ):
        raise RuntimeStorageError("Chiave storage relativa non valida.")
    return key.as_posix()


def resolve_storage_key(namespace: str, value: str) -> Path:
    namespace_root = (storage_root() / safe_relative_key(namespace)).resolve()
    target = (namespace_root / safe_relative_key(value)).resolve()
    if namespace_root != target.parent and namespace_root not in target.parents:
        raise RuntimeStorageError("Chiave storage fuori dal namespace.")
    return target


def atomic_write(namespace: str, value: str, content: bytes) -> Path:
    target = resolve_storage_key(namespace, value)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RuntimeStorageError("Collisione della chiave storage.")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            raise RuntimeStorageError("Collisione della chiave storage.")
        os.replace(temporary_path, target)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return target
