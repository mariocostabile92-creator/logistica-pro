import json
import re
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.database import PostgresConnection, db_session
from app.demo import repository as demo_repository
from app.demo import service as demo_service
from app.demo import settings as demo_settings
from app.demo.dataset_factory import (
    DEMO_CREATED_BY,
    DEMO_DATASET_VERSION,
    DEMO_WORKSPACE_ID,
    build_demo_dataset,
    demo_import_filenames,
)
from app.main import app
from app.plugins.fleet.application.asset_service import create_asset
from app.plugins.fleet.infrastructure.repository import get_asset
from app.repositories.import_repository import get_import, save_import
from app.repositories.planning_repository import get_planning_record
from app.schemas.planning_schema import GeneratePlanningRequest
from app.services.planning_generation_service import generate_planning
from tests.planning_helpers import save_normalized_imports, simple_rows


client = TestClient(app)
BASE_URL = "/api/demo/v1"


def _database_count(table: str) -> int:
    allowed = {
        "assignments",
        "fleet_assets",
        "imports",
        "operation_snapshots",
        "planning_events",
        "plannings",
    }
    assert table in allowed
    with db_session() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS total FROM {table}"
        ).fetchone()
    return int(row["total"])


def _load_demo() -> dict[str, object]:
    response = client.post(f"{BASE_URL}/load")
    assert response.status_code == 200, response.text
    return response.json()


def test_status_is_hidden_when_demo_is_disabled(monkeypatch):
    monkeypatch.setenv("DEMO_WORKSPACE_ENABLED", "false")

    assert client.get(f"{BASE_URL}/status").status_code == 404
    assert client.post(f"{BASE_URL}/load").status_code == 404
    assert client.post(f"{BASE_URL}/reset").status_code == 404


def test_production_default_is_disabled_until_explicitly_enabled(
    monkeypatch,
):
    monkeypatch.setattr(
        demo_settings,
        "SETTINGS",
        SimpleNamespace(production=True),
    )

    assert demo_settings.demo_workspace_enabled({}) is False
    assert demo_settings.demo_workspace_enabled(
        {"DEMO_WORKSPACE_ENABLED": "true"}
    ) is True
    assert demo_settings.demo_workspace_enabled(
        {"DEMO_WORKSPACE_ENABLED": "invalid"}
    ) is False


def test_status_without_demo_is_explicit():
    response = client.get(f"{BASE_URL}/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "present": False,
        "status": "no_demo",
        "summary": None,
    }


def test_load_creates_the_deterministic_workspace():
    payload = _load_demo()
    summary = payload["summary"]

    assert payload["created"] is True
    assert payload["idempotent"] is False
    assert summary["demo_workspace_id"] == DEMO_WORKSPACE_ID
    assert summary["dataset_version"] == DEMO_DATASET_VERSION
    assert summary["is_demo"] is True
    assert summary["operation_date"] == "2099-01-15"
    assert summary["counts"]["tasks"] == 10
    assert summary["counts"]["human_resources"] == 12
    assert summary["counts"]["assets"] == 11
    assert summary["counts"]["time_windows"] == 2
    assert summary["planning_id"] is not None


def test_load_is_idempotent_and_does_not_duplicate_records():
    first = _load_demo()
    before = {
        table: _database_count(table)
        for table in ("imports", "fleet_assets", "plannings")
    }

    second = _load_demo()

    assert second["created"] is False
    assert second["idempotent"] is True
    assert second["summary"]["planning_id"] == first["summary"]["planning_id"]
    assert {
        table: _database_count(table)
        for table in before
    } == before


def test_dataset_uses_real_import_pipeline_and_synthetic_identifiers():
    _load_demo()
    record = demo_repository.get_workspace(DEMO_WORKSPACE_ID)
    planning_import = get_import(record["metadata"]["import_ids"][0])
    fleet_import = get_import(record["metadata"]["import_ids"][1])

    assert planning_import["original_filename"].startswith("DEMO__")
    assert fleet_import["original_filename"].startswith("DEMO__")
    assert len(planning_import["normalized_rows"]) == 10
    assert len(fleet_import["normalized_rows"]) == 11
    assert {
        row["route"] for row in planning_import["normalized_rows"]
    } == {
        f"TASK-DEMO-{index:03d}" for index in range(1, 11)
    }
    assert {
        row["cycle"] for row in planning_import["normalized_rows"]
    } == {"WAVE-DEMO-A", "WAVE-DEMO-B"}
    assert sum(
        row["status"] == "Manutenzione"
        for row in fleet_import["normalized_rows"]
    ) == 1
    assert sum(
        row["status"] == "Riserva"
        for row in fleet_import["normalized_rows"]
    ) == 1


def test_demo_exposes_warnings_capacity_and_yellow_readiness():
    summary = _load_demo()["summary"]

    assert summary["planning_status"] == "ready"
    assert summary["readiness_status"] == "yellow"
    assert "LOW_RESERVE_MARGIN" in summary["warning_codes"]
    assert summary["counts"]["warnings"] >= 1
    assert summary["counts"]["alternatives"] >= 1
    assert summary["counts"]["events"] >= 1


def test_demo_planning_is_complete_and_records_driver_absence():
    summary = _load_demo()["summary"]
    planning_id = summary["planning_id"]

    response = client.get(f"/api/planning/{planning_id}")

    assert response.status_code == 200
    planning = response.json()
    assert len(planning["assignments"]) == 10
    assert all(item["driver_id"] for item in planning["assignments"])
    assert all(item["plate"] for item in planning["assignments"])
    first_task = next(
        item
        for item in planning["assignments"]
        if item["route_id"] == "TASK-DEMO-001"
    )
    assert first_task["driver_name"] == "Demo Driver 11"
    assert "DRIVER_ABSENT_REPLACED" in first_task["warnings"]
    assert any(item["alternatives"] for item in planning["assignments"])
    assert planning["history"]["events"][0]["event_type"] == "driver_absent"

    exported = client.get(f"/api/planning/{planning_id}/export?format=csv")
    assert exported.status_code == 200
    assert "TASK-DEMO-001" in exported.text


def test_status_after_load_returns_the_persisted_summary():
    loaded = _load_demo()

    status = client.get(f"{BASE_URL}/status")

    assert status.status_code == 200
    assert status.json()["present"] is True
    assert status.json()["status"] == "ready"
    assert status.json()["summary"] == loaded["summary"]


def test_reset_removes_all_and_only_registered_demo_data():
    _load_demo()

    response = client.post(f"{BASE_URL}/reset")

    assert response.status_code == 200
    assert response.json()["idempotent"] is False
    assert response.json()["removed"] == {
        "imports": 2,
        "plannings": 1,
        "operation_snapshots": 1,
        "fleet_assets": 11,
    }
    assert _database_count("imports") == 0
    assert _database_count("plannings") == 0
    assert _database_count("assignments") == 0
    assert _database_count("planning_events") == 0
    assert _database_count("operation_snapshots") == 0
    assert _database_count("fleet_assets") == 0
    status = client.get(f"{BASE_URL}/status").json()
    assert status["present"] is False
    assert status["status"] == "reset"


def test_reset_is_idempotent():
    _load_demo()
    assert client.post(f"{BASE_URL}/reset").status_code == 200

    second = client.post(f"{BASE_URL}/reset")

    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert not any(second.json()["removed"].values())


def test_reset_preserves_non_demo_imports_planning_and_assets():
    real_rows = simple_rows(routes=1, drivers=1, vehicles=2)
    real_import_ids = save_normalized_imports(*real_rows)
    real_planning = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=real_import_ids[0],
            fleet_import_id=real_import_ids[1],
            operation_date="2026-07-20",
        )
    )
    real_asset = create_asset(
        {
            "external_identifier": "asset-real-001",
            "plate": "REAL001",
            "category": "light_van",
            "status": "active",
            "availability": "available",
            "notes": "Synthetic non-demo test record",
            "capabilities": [],
        },
        actor="test_operator",
    )
    _load_demo()

    reset = client.post(f"{BASE_URL}/reset")

    assert reset.status_code == 200
    assert get_import(real_import_ids[0]) is not None
    assert get_import(real_import_ids[1]) is not None
    assert get_planning_record(real_planning.planning.id) is not None
    assert get_asset(real_asset.id) is not None


def test_reset_preserves_non_demo_import_with_colliding_filename():
    planning_filename, _ = demo_import_filenames(build_demo_dataset())
    colliding_import_id = save_import(
        dataset_type="planning",
        original_filename=planning_filename,
        sheet_name=None,
        column_mapping=[],
        normalized_rows=[
            {
                "row_number": 2,
                "route": "SYNTHETIC-NON-DEMO-TASK",
            }
        ],
    )
    _load_demo()

    reset = client.post(f"{BASE_URL}/reset")

    assert reset.status_code == 200
    assert reset.json()["removed"]["imports"] == 2
    assert get_import(colliding_import_id) is not None


def test_partial_failure_is_compensated_and_can_be_retried(monkeypatch):
    original_create_asset = demo_service.create_asset
    calls = 0

    def fail_on_second_asset(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Synthetic failure")
        return original_create_asset(*args, **kwargs)

    monkeypatch.setattr(
        demo_service,
        "create_asset",
        fail_on_second_asset,
    )

    failed = client.post(f"{BASE_URL}/load")

    assert failed.status_code == 500
    assert failed.json()["detail"]["code"] == "DEMO_LOAD_FAILED"
    assert _database_count("imports") == 0
    assert _database_count("fleet_assets") == 0
    assert _database_count("plannings") == 0
    assert demo_repository.get_workspace(DEMO_WORKSPACE_ID)["status"] == "failed"

    monkeypatch.setattr(
        demo_service,
        "create_asset",
        original_create_asset,
    )
    retried = client.post(f"{BASE_URL}/load")
    assert retried.status_code == 200
    assert retried.json()["summary"]["status"] == "ready"


def test_dataset_contains_no_personal_data_or_real_company_codes():
    dataset = build_demo_dataset()
    serialized = json.dumps(dataset.model_dump(mode="json"))

    assert "@" not in serialized
    assert not re.search(r"\b(?:\+39)?3\d{9}\b", serialized)
    assert all(
        item.display_name.startswith("Demo Driver ")
        for item in dataset.human_resources
    )
    assert all(
        item.external_identifier.startswith("DRV-DEMO-")
        for item in dataset.human_resources
    )
    assert all(
        item.external_identifier.startswith("AST-DEMO-")
        for item in dataset.assets
    )
    assert dataset.operational_unit == "HUB-NORD-01"
    assert dataset.organization == "Demo Logistics Italia"


def test_repository_statements_use_the_postgres_compatibility_layer(
    monkeypatch,
):
    class FakeCursor:
        description = ()

        def __init__(self):
            self.statements = []

        def execute(self, statement, parameters):
            self.statements.append((statement, parameters))

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()

        def cursor(self):
            return self.cursor_instance

    raw = FakeConnection()
    postgres = PostgresConnection(raw)

    @contextmanager
    def fake_session():
        yield postgres

    monkeypatch.setattr(demo_repository, "db_session", fake_session)
    demo_repository.init_schema()
    demo_repository.save_workspace(
        demo_workspace_id=DEMO_WORKSPACE_ID,
        dataset_version=DEMO_DATASET_VERSION,
        status="loading",
        created_at="2099-01-01T00:00:00+00:00",
        created_by=DEMO_CREATED_BY,
        updated_at="2099-01-01T00:00:00+00:00",
        metadata={},
    )

    statements = [
        statement
        for statement, _ in raw.cursor_instance.statements
    ]
    assert any("CREATE TABLE IF NOT EXISTS demo_workspaces" in item for item in statements)
    insert = next(item for item in statements if "INSERT INTO demo_workspaces" in item)
    assert "%s" in insert
    assert "ON CONFLICT (demo_workspace_id)" in insert


def test_demo_import_filenames_are_deterministic_and_versioned():
    dataset = build_demo_dataset()

    first = demo_import_filenames(dataset)
    second = demo_import_filenames(build_demo_dataset())

    assert first == second
    assert all(DEMO_DATASET_VERSION in item for item in first)
