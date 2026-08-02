from pathlib import Path, PurePosixPath

from fastapi.testclient import TestClient

from app.attachments import service
from app.attachments.storage import LocalAttachmentStorage
from app.core.database import db_session
from app.main import app
from conftest import TEST_STORAGE_ROOT


client = TestClient(app)
BASE = "/api/attachments"
ASSETS = "/api/plugins/fleet/v1/assets"
DOCUMENTS = "/api/fleet/documents"
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload(entity_type: str, entity_id: int, name: str, content: bytes, mime: str):
    return client.post(BASE, data={
        "entity_type": entity_type, "entity_id": entity_id,
        "created_by": "fleet_manager", "notes": "Test allegato",
    }, files={"file": (name, content, mime)})


def create_vehicle(identifier: str, plate: str):
    return client.post(ASSETS, json={
        "external_identifier": identifier, "plate": plate,
        "category": "Furgone", "status": "active",
        "availability": "available", "capabilities": [],
    }).json()


def create_document(vehicle_id: int):
    return client.post(DOCUMENTS, json={
        "vehicle_id": vehicle_id, "document_type": "assicurazione",
        "title": "Polizza RCA", "document_number": None, "issuer": None,
        "issued_at": None, "expires_at": None, "notes": None,
        "status": "valido", "file_name": None, "file_reference": None,
    }).json()


def test_upload_list_download_preview_delete_and_multiple_entities():
    vehicle = create_vehicle("ATT-MULTI-01", "AM001AA")
    document = create_document(vehicle["id"])
    first = upload("vehicle", vehicle["id"], "foto.png", PNG, "image/png")
    second = upload("document", document["id"], "polizza.pdf", PDF, "application/pdf")
    assert first.status_code == second.status_code == 201
    photo, policy = first.json(), second.json()
    assert photo["stored_filename"] != policy["stored_filename"]
    assert photo["preview_available"] is True
    assert client.get(photo["download_url"]).content == PNG
    preview = client.get(policy["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("application/pdf")
    listing = client.get(BASE, params={"entity_type": "vehicle", "entity_id": vehicle["id"]}).json()
    assert listing["count"] == 1
    assert listing["items"][0]["id"] == photo["id"]
    assert client.delete(f"{BASE}/{photo['id']}").status_code == 204
    assert client.get(photo["download_url"]).status_code == 404
    assert client.delete(f"{BASE}/{policy['id']}").status_code == 204


def test_vehicle_aggregation_reads_shared_records_without_copying():
    vehicle = create_vehicle("ATT-VAN-01", "AT001AA")
    document = create_document(vehicle["id"])
    before = client.get("/api/fleet/vision", params={"vehicle_id": vehicle["id"]}).json()
    assert before["items"][0]["missing_documents"] == 1
    assert client.get(DOCUMENTS, params={"vehicle_id": vehicle["id"]}).json()["summary"]["missing_files"] == 1
    direct = upload("vehicle", vehicle["id"], "mezzo.png", PNG, "image/png").json()
    linked = upload("document", document["id"], "documento.pdf", PDF, "application/pdf").json()
    assert client.get(f"{DOCUMENTS}/{document['id']}").json()["has_file"] is True
    aggregated = client.get(f"{BASE}/vehicle/{vehicle['id']}").json()
    assert aggregated["count"] == 2
    assert {item["id"] for item in aggregated["items"]} == {direct["id"], linked["id"]}
    assert client.get(BASE, params={
        "entity_type": "document", "entity_id": document["id"],
    }).json()["items"][0]["id"] == linked["id"]
    after = client.get("/api/fleet/vision", params={"vehicle_id": vehicle["id"]}).json()
    assert after["items"][0]["missing_documents"] == 0
    assert client.get(DOCUMENTS, params={"vehicle_id": vehicle["id"]}).json()["summary"]["missing_files"] == 0
    client.delete(f"{BASE}/{direct['id']}")
    client.delete(f"{BASE}/{linked['id']}")


def test_rejects_unsupported_or_spoofed_files():
    vehicle = create_vehicle("ATT-INVALID-01", "AI001AA")
    unsupported = upload("vehicle", vehicle["id"], "script.exe", b"MZ", "application/octet-stream")
    spoofed = upload("vehicle", vehicle["id"], "fake.png", b"not-a-png", "image/png")
    unknown_entity = upload("unknown", 1, "file.pdf", PDF, "application/pdf")
    assert unsupported.status_code == 422
    assert spoofed.status_code == 422
    assert unknown_entity.status_code == 422


def test_upload_rejects_oversize_before_buffering_more_than_the_limit(monkeypatch):
    vehicle = create_vehicle("ATT-LIMIT-01", "AL001AA")
    monkeypatch.setattr("app.attachments.router.MAX_UPLOAD_SIZE_BYTES", 16)
    response = upload("vehicle", vehicle["id"], "large.pdf", PDF + b"x" * 32, "application/pdf")
    assert response.status_code == 413
    assert response.json() == {"detail": "Il file supera la dimensione massima consentita."}


def test_upload_normalizes_path_traversal_filename():
    vehicle = create_vehicle("ATT-PATH-01", "AX001AA")
    item = upload("vehicle", vehicle["id"], "../../segreto.png", PNG, "image/png").json()
    try:
        assert item["original_filename"] == "segreto.png"
        assert ".." not in item["storage_path"]
        assert "\\" not in item["storage_path"]
    finally:
        client.delete(f"{BASE}/{item['id']}")


def test_scoped_reads_never_claim_unowned_legacy_attachment():
    vehicle = create_vehicle("ATT-LEGACY-01", "AG001AA")
    with db_session() as conn:
        conn.execute(
            """INSERT INTO attachments
            (id,entity_type,entity_id,original_filename,stored_filename,mime_type,size,
             created_at,created_by,storage_path,preview_available,notes,organization_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
            ("legacy-unowned", "vehicle", vehicle["id"], "legacy.png", "legacy.png",
             "image/png", len(PNG), "2026-08-02T00:00:00+00:00", "legacy",
             "legacy/legacy.png", 1, None),
        )
    assert client.get(BASE, params={
        "entity_type": "vehicle", "entity_id": vehicle["id"],
    }).json() == {"items": [], "count": 0}
    with db_session() as conn:
        row = conn.execute("SELECT organization_id FROM attachments WHERE id='legacy-unowned'").fetchone()
        assert row["organization_id"] is None


def test_damage_and_maintenance_files_use_relative_atomic_persistent_keys():
    vehicle = create_vehicle("ATT-PERSIST-01", "AP001AA")
    damage = client.post("/api/fleet/damage-cases", json={
        "vehicle_id": vehicle["id"], "occurred_at": "2026-08-02T10:00:00Z",
        "origin": "manual", "manual_reason": "QA persistenza",
        "description": "Foto danno QA", "severity": "media",
        "vehicle_operational_status": "indisponibile",
    }).json()
    maintenance = client.post("/api/fleet/maintenances", json={
        "vehicle_id": vehicle["id"], "description": "Fattura QA",
        "maintenance_type": "meccanica", "status": "aperta", "priority": "media",
    }).json()
    photo = upload("damage", damage["id"], "danno.png", PNG, "image/png").json()
    invoice = upload("maintenance", maintenance["id"], "fattura.pdf", PDF, "application/pdf").json()

    for item, expected in ((photo, PNG), (invoice, PDF)):
        key = item["storage_path"]
        assert PurePosixPath(key).is_absolute() is False
        assert ":" not in key and "\\" not in key and key.count("/") == 2
        assert LocalAttachmentStorage(TEST_STORAGE_ROOT / "attachments").read(key) == expected
        assert client.get(item["preview_url"]).content == expected
        assert client.get(item["download_url"]).content == expected
    assert list((TEST_STORAGE_ROOT / "attachments").rglob("*.tmp")) == []
    assert client.delete(f"/api/attachments/{photo['id']}").status_code == 204
    with db_session() as conn:
        rows = conn.execute(
            "SELECT organization_id,action FROM attachment_events ORDER BY created_at"
        ).fetchall()
    assert [(row["organization_id"], row["action"]) for row in rows] == [
        ("test-organization", "uploaded"), ("test-organization", "uploaded"),
        ("test-organization", "deleted"),
    ]


def test_attachment_organization_isolation_and_missing_file_message():
    vehicle = create_vehicle("ATT-ORG-01", "AO001AA")
    item = service.upload(
        "vehicle", vehicle["id"], "isolata.png", "image/png", PNG,
        "user-org-a", None, "organization-a",
    )
    try:
        assert service.get(item["id"], "organization-a")["organization_id"] == "organization-a"
        try:
            service.get(item["id"], "organization-b")
            raise AssertionError("Un'altra organizzazione non deve leggere l'allegato")
        except service.AttachmentError as exc:
            assert exc.status_code == 404

        physical = TEST_STORAGE_ROOT / "attachments" / Path(item["storage_path"])
        physical.unlink()
        missing = client.get(item["download_url"])
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Allegato non trovato."}
        # The harness organization cannot see an attachment owned by organization-a;
        # the owner receives the storage-specific message through the service contract.
        try:
            service.resolve_file(item["id"], "organization-a")
            raise AssertionError("Il file fisico e stato rimosso")
        except service.AttachmentError as exc:
            assert str(exc) == "File non disponibile nello storage."
    finally:
        with db_session() as conn:
            conn.execute("DELETE FROM attachments WHERE id=?", (item["id"],))


def test_cross_organization_attachment_read_download_and_delete_are_denied():
    vehicle = create_vehicle("ATT-ORG-GUARD-01", "OG001AA")
    item = service.upload(
        "vehicle", vehicle["id"], "protetta.png", "image/png", PNG,
        "user-org-a", None, "organization-a",
    )
    try:
        assert service.list_items("vehicle", vehicle["id"], "organization-b") == {
            "items": [], "count": 0,
        }
        for operation in (
            lambda: service.resolve_file(item["id"], "organization-b"),
            lambda: service.delete(item["id"], "organization-b", "user-org-b"),
        ):
            try:
                operation()
                raise AssertionError("L'operazione cross-organization deve essere negata")
            except service.AttachmentError as exc:
                assert exc.status_code == 404
        assert service.get(item["id"], "organization-a")["id"] == item["id"]
    finally:
        try:
            service.delete(item["id"], "organization-a", "user-org-a")
        except service.AttachmentError:
            pass


def test_document_foreign_id_cannot_receive_an_attachment_from_another_organization():
    vehicle = create_vehicle("ATT-ORG-DOC-01", "OD001AA")
    document = create_document(vehicle["id"])
    try:
        service.upload(
            "document", document["id"], "estranea.pdf", "application/pdf", PDF,
            "user-org-b", None, "organization-b",
        )
        raise AssertionError("Un documento di un'altra organizzazione non deve essere scrivibile")
    except service.AttachmentError as exc:
        assert exc.status_code == 404
