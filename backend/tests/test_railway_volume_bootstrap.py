import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.attachments.storage import LocalAttachmentStorage
from app.core import runtime_storage
from app.core.config import DATA_DIR, load_settings
from app.plugins.fleet.journal.infrastructure.storage import PrivateLocalMediaStorage


ROOT = Path(__file__).resolve().parents[2]


def settings(root: Path, required: bool = False):
    return SimpleNamespace(runtime_storage_root=root, require_persistent_storage=required)


def test_runtime_root_absent_is_created_and_verified(tmp_path, monkeypatch):
    root = tmp_path / "new-runtime"
    monkeypatch.setattr(runtime_storage, "SETTINGS", settings(root))
    assert runtime_storage.initialize_runtime_storage() == root
    assert root.is_dir()
    assert not list(root.glob(".storage-probe-*"))


def test_existing_runtime_root_remains_writable(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setattr(runtime_storage, "SETTINGS", settings(root))
    runtime_storage.initialize_runtime_storage()
    probe = root / "application-write.txt"
    probe.write_text("operations", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "operations"


def test_journal_and_attachment_namespaces_use_the_runtime_root(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    monkeypatch.setattr(runtime_storage, "SETTINGS", settings(root))
    runtime_storage.initialize_runtime_storage()
    journal = PrivateLocalMediaStorage()
    key = journal.save("2026/08/media.jpg", b"journal")
    attachment = LocalAttachmentStorage(root / "attachments")
    attachment_key = attachment.save("attachment.pdf", b"attachment")
    assert key == "2026/08/media.jpg"
    assert attachment_key == "attachment.pdf"
    assert not Path(key).is_absolute()
    assert journal.path(key).read_bytes() == b"journal"
    assert attachment.read(attachment_key) == b"attachment"
    assert (root / "journal_media").is_dir()
    assert (root / "attachments").is_dir()


def test_required_storage_accepts_explicit_valid_root(tmp_path, monkeypatch):
    root = tmp_path / "persistent"
    monkeypatch.setenv("RUNTIME_STORAGE_ROOT", str(root))
    monkeypatch.setattr(runtime_storage, "SETTINGS", settings(root, required=True))
    assert runtime_storage.initialize_runtime_storage() == root


def test_required_storage_rejects_missing_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNTIME_STORAGE_ROOT", raising=False)
    monkeypatch.setattr(runtime_storage, "SETTINGS", settings(tmp_path / "runtime", required=True))
    with pytest.raises(runtime_storage.RuntimeStorageError, match="RUNTIME_STORAGE_ROOT"):
        runtime_storage.initialize_runtime_storage()


def test_local_fallback_is_preserved_when_persistence_is_optional():
    loaded = load_settings({"APP_ENV": "test"})
    assert loaded.runtime_storage_root == DATA_DIR.resolve()
    assert loaded.require_persistent_storage is False


def test_entrypoint_prepares_only_approved_roots_and_drops_privileges():
    script = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    for expected in [
        "set -eu", "/data|/data/*", "/app/backend/data",
        '"$RUNTIME_ROOT/journal_media"', '"$RUNTIME_ROOT/attachments"',
        "install -d -m 0770", 'exec gosu "$APPLICATION_USER:$APPLICATION_GROUP" "$@"',
        "verify_runtime_storage", 'exec "$@"',
    ]:
        assert expected in script
    assert "chmod 777" not in script
    assert "chown -R" not in script
    assert "RAILWAY_RUN_UID" not in script


def test_dockerfile_keeps_root_only_for_entrypoint_bootstrap():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    railway_text = (ROOT / "railway.json").read_text(encoding="utf-8")
    railway = json.loads(railway_text)
    assert "apt-get install -y --no-install-recommends gosu" in dockerfile
    assert "COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/operations-entrypoint" in dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/operations-entrypoint"]' in dockerfile
    assert "USER operations" not in dockerfile
    assert railway["deploy"]["startCommand"].startswith(
        "/usr/local/bin/operations-entrypoint sh -c \"exec python -m uvicorn "
    )
    assert "RAILWAY_RUN_UID" not in dockerfile + railway_text


def test_entrypoint_is_forced_to_lf_and_has_no_crlf_bytes():
    script = (ROOT / "docker" / "entrypoint.sh").read_bytes()
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert script.startswith(b"#!/bin/sh\n")
    assert b"\r\n" not in script
    assert "docker/*.sh text eol=lf" in attributes
