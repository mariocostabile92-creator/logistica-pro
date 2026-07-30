from fastapi.testclient import TestClient

from app.main import app


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
