from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.plugins.fleet.documents.infrastructure import repository


client = TestClient(app)
ASSETS = "/api/plugins/fleet/v1/assets"
DOCUMENTS = "/api/fleet/documents"


def asset(identifier: str = "DOC-VAN-01"):
    response = client.post(ASSETS, json={
        "external_identifier": identifier,
        "plate": "DC123AA",
        "category": "Furgone",
        "status": "active",
        "availability": "available",
        "capabilities": [],
    })
    assert response.status_code == 201
    return response.json()


def payload(vehicle_id: int, **changes):
    return {
        "vehicle_id": vehicle_id,
        "document_type": "assicurazione",
        "title": "Polizza RCA",
        "document_number": "RCA-2026-01",
        "issuer": "Assicurazioni Italia",
        "issued_at": "2026-01-01",
        "expires_at": "2026-12-31",
        "notes": "Documento originale",
        "status": "valido",
        "file_name": None,
        "file_reference": None,
        **changes,
    }


def test_create_list_detail_update_search_and_combined_filters():
    vehicle = asset()
    created = client.post(DOCUMENTS, json=payload(vehicle["id"]))
    assert created.status_code == 201
    item = created.json()
    assert item["plate"] == "DC123AA"
    assert item["has_file"] is False
    assert item["uploaded_at"] is None

    detail = client.get(f"{DOCUMENTS}/{item['id']}")
    assert detail.status_code == 200
    assert detail.json()["document_number"] == "RCA-2026-01"

    updated = client.patch(f"{DOCUMENTS}/{item['id']}", json={
        "title": "Polizza RCA aggiornata",
        "status": "in_scadenza",
        "issuer": "Assicurazioni Italia",
    })
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_scadenza"

    listing = client.get(DOCUMENTS, params={
        "search": "dc123",
        "status": "in_scadenza",
        "document_type": "assicurazione",
        "has_file": False,
    }).json()
    assert [entry["id"] for entry in listing["items"]] == [item["id"]]
    assert listing["summary"]["total"] >= 1
    assert listing["summary"]["missing_files"] >= 1


def test_without_expiry_optional_file_types_status_and_vehicle_link():
    vehicle = asset("DOC-VAN-02")
    manual = client.post(DOCUMENTS, json=payload(
        vehicle["id"],
        document_type="manuale",
        title="Manuale del veicolo",
        document_number=None,
        expires_at=None,
        status="senza_scadenza",
    ))
    assert manual.status_code == 201
    assert manual.json()["expires_at"] is None

    assert client.post(
        DOCUMENTS,
        json=payload(vehicle["id"], document_type="fattura"),
    ).status_code == 422
    assert client.post(
        DOCUMENTS,
        json=payload(vehicle["id"], status="ignoto"),
    ).status_code == 422
    assert client.post(DOCUMENTS, json=payload(999999)).status_code == 404


def test_contract_document_links_profile_without_duplicating_economic_data():
    vehicle = asset("DOC-VAN-03")
    profile = client.put(f"{ASSETS}/{vehicle['id']}/profile", json={
        "contract_type": "lungo_termine",
        "company": "Mobilità Italia",
        "contract_number": "LT-DOC-01",
        "monthly_fee": "750.00",
        "deductible": "500.00",
        "included_km": 120000,
        "starts_on": "2026-01-01",
        "expires_on": "2029-12-31",
        "contract_status": "attivo",
    })
    assert profile.status_code == 200
    document = client.post(DOCUMENTS, json=payload(
        vehicle["id"],
        document_type="contratto_noleggio",
        title="Contratto LT",
    )).json()
    assert document["contract_link"] == {
        "contract_type": "lungo_termine",
        "contract_number": "LT-DOC-01",
    }
    assert "monthly_fee" not in document
    assert "deductible" not in document


def test_schema_is_idempotent_and_contains_no_sqlite_only_migration():
    repository.init_schema()
    repository.init_schema()
    source = Path(repository.__file__).read_text(encoding="utf-8")
    assert "PRAGMA" not in source
