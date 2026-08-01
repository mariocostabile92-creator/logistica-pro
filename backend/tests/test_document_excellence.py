from datetime import timedelta

from fastapi.testclient import TestClient

from app.auth.domain import Role
from app.auth.password_service import hash_password
from app.auth.repository import create_user
from app.core.database import db_session
from app.main import app
from app.plugins.fleet.documents.domain.status_evaluator import evaluate_document, organization_today


PASSWORD = "Password-sicura-123"
ENFORCE = {"X-Auth-Enforce": "1"}
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"


def authenticated(email: str, role: Role, organization: str) -> TestClient:
    create_user(email, hash_password(PASSWORD), role, organization)
    client = TestClient(app)
    assert client.post("/api/auth/login", headers=ENFORCE, json={
        "email": email, "password": PASSWORD, "remember_me": False,
    }).status_code == 200
    return client


def vehicle(client: TestClient):
    response = client.post("/api/plugins/fleet/v1/assets", headers=ENFORCE, json={
        "external_identifier": "P03-DOC", "plate": "P03DOC", "category": "Van",
        "status": "active", "availability": "available", "capabilities": [],
    })
    assert response.status_code == 201
    return response.json()


def document(client: TestClient, vehicle_id: int, **changes):
    payload = {"vehicle_id": vehicle_id, "document_type": "carta_circolazione",
               "title": "Carta di circolazione", "document_number": "CC-P03",
               "issuer": "MIT", "issued_at": None, "expires_at": None, "notes": None,
               **changes}
    return client.post("/api/fleet/documents", headers=ENFORCE, json=payload)


def test_status_evaluator_is_single_timezone_aware_rule():
    today = organization_today("Europe/Rome")
    base = {"attachment_count": 1, "file_reference": None, "archived_at": None}
    assert evaluate_document({**base, "expires_at": None}, "Europe/Rome", today)["status"] == "senza_scadenza"
    assert evaluate_document({**base, "attachment_count": 0, "expires_at": None}, "Europe/Rome", today)["status"] == "file_mancante"
    assert evaluate_document({**base, "expires_at": str(today - timedelta(days=1))}, "Europe/Rome", today)["status"] == "scaduto"
    assert evaluate_document({**base, "expires_at": str(today + timedelta(days=30))}, "Europe/Rome", today)["status"] == "in_scadenza"
    assert evaluate_document({**base, "expires_at": str(today + timedelta(days=31))}, "Europe/Rome", today)["status"] == "completo"


def test_document_attachment_changes_real_status_duplicate_archive_and_audit():
    admin = authenticated("admin-doc@example.test", Role.ADMINISTRATOR, "Org Documenti")
    asset = vehicle(admin)
    created = document(admin, asset["id"])
    assert created.status_code == 201 and created.json()["status"] == "file_mancante"
    assert document(admin, asset["id"]).status_code == 409
    document_id = created.json()["id"]
    uploaded = admin.post("/api/attachments", headers=ENFORCE,
                          data={"entity_type": "document", "entity_id": document_id},
                          files={"file": ("carta.pdf", PDF, "application/pdf")})
    assert uploaded.status_code == 201
    assert admin.get(f"/api/fleet/documents/{document_id}", headers=ENFORCE).json()["status"] == "senza_scadenza"
    updated = admin.patch(f"/api/fleet/documents/{document_id}", headers=ENFORCE,
                          json={"title": "Carta aggiornata", "notes": "Verificata"})
    assert updated.status_code == 200 and updated.json()["title"] == "Carta aggiornata"
    archived = admin.post(f"/api/fleet/documents/{document_id}/archive", headers=ENFORCE)
    assert archived.status_code == 200 and archived.json()["status"] == "archiviato"
    with db_session() as conn:
        actions = {row["action"] for row in conn.execute("SELECT action FROM fleet_document_events").fetchall()}
    assert {"document.created", "document.updated", "document.archived"} <= actions


def test_organization_isolation_and_viewer_read_only_apply_to_documents_and_files():
    owner = authenticated("owner-doc@example.test", Role.FLEET_MANAGER, "Owner Org")
    asset = vehicle(owner)
    created = document(owner, asset["id"], title="Documento isolato")
    assert created.status_code == 201
    attachment = owner.post("/api/attachments", headers=ENFORCE,
                            data={"entity_type": "document", "entity_id": created.json()["id"]},
                            files={"file": ("isolato.pdf", PDF, "application/pdf")}).json()
    viewer = authenticated("viewer-doc@example.test", Role.VIEWER, "Other Org")
    assert viewer.get(f"/api/fleet/documents/{created.json()['id']}", headers=ENFORCE).status_code == 404
    assert viewer.get(f"/api/attachments/{attachment['id']}/download", headers=ENFORCE).status_code == 404
    assert document(viewer, asset["id"], title="Vietato").status_code == 403
    assert viewer.post("/api/attachments", headers=ENFORCE,
                       data={"entity_type": "document", "entity_id": created.json()["id"]},
                       files={"file": ("no.pdf", PDF, "application/pdf")}).status_code == 403


def test_unauthenticated_document_api_is_protected():
    assert TestClient(app).get("/api/fleet/documents", headers=ENFORCE).status_code == 401
