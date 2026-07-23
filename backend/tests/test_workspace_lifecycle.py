import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.configuration.models import ConfigurationScope
from app.core.configuration.service import create_configuration_version
from app.core.database import PostgresConnection, db_session
from app.demo.dataset_factory import DEMO_WORKSPACE_ID
from app.main import app
from app.plugins.fleet.application.asset_service import (
    add_document,
    create_asset,
)
from app.repositories.import_repository import save_analysis, save_import
from app.schemas.planning_schema import GeneratePlanningRequest
from app.services.planning_generation_service import generate_planning
from app.workspace import repository as workspace_repository
from app.workspace import reset_service
from app.workspace.models import WorkspaceState
from app.workspace.status_service import get_workspace_status
from tests.planning_helpers import save_normalized_imports, simple_rows


client = TestClient(app)
BASE_URL = "/api/workspace/v1"
PRE_WORKSPACE_PATHS_SHA256 = (
    "3f50f1bcf28109bd816a25e7723abab917b945275aaa4d7c8fc7655730395d9a"
)


def _count(table: str) -> int:
    allowed = {
        *workspace_repository.OPERATIONAL_DELETE_ORDER,
        *workspace_repository.PRESERVED_TABLES,
    }
    assert table in allowed
    with db_session() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS total FROM {table}"
        ).fetchone()
    return int(row["total"])


def _production_imports() -> tuple[int, int]:
    return save_normalized_imports(
        *simple_rows(routes=2, drivers=3, vehicles=3)
    )


def _production_workspace():
    planning_import_id, fleet_import_id = _production_imports()
    planning = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_import_id,
            fleet_import_id=fleet_import_id,
            operation_date="2026-07-20",
        )
    )
    asset = create_asset(
        {
            "external_identifier": "asset-production-001",
            "plate": "PR001AA",
            "category": "light_van",
            "status": "active",
            "availability": "available",
            "notes": "Synthetic production fixture",
            "capabilities": ["electric"],
        },
        actor="test_operator",
    )
    add_document(
        asset.id,
        {
            "document_type": "insurance",
            "name": "Synthetic policy",
            "reference": "POLICY-001",
            "issued_on": "2026-01-01",
            "expires_on": "2027-01-01",
            "notes": None,
        },
        actor="test_operator",
    )
    return planning, asset


def _configuration_version() -> int:
    revision = create_configuration_version(
        ConfigurationScope(organization_id="workspace-test"),
        [
            {
                "key": "nomenclature",
                "values": [
                    {"key": "asset_label", "value": "Equipment"},
                ],
            },
            {
                "key": "reserve_policy",
                "values": [
                    {"key": "default_threshold", "value": 3},
                ],
            },
        ],
        created_by="workspace-test",
    )
    return revision.version.number


def test_status_empty_is_typed_and_actionable():
    response = client.get(f"{BASE_URL}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_state"] == "EMPTY"
    assert payload["is_demo"] is False
    assert payload["can_reset"] is False
    assert payload["task_count"] == 0
    assert payload["asset_count"] == 0
    assert payload["latest_planning_import"] is None
    assert "import_data" in payload["available_actions"]


def test_status_demo_uses_persisted_registry_provenance():
    loaded = client.post("/api/demo/v1/load")
    assert loaded.status_code == 200

    status = client.get(f"{BASE_URL}/status").json()

    assert status["workspace_state"] == "DEMO"
    assert status["is_demo"] is True
    assert status["mixed_data_detected"] is False
    assert status["task_count"] == 10
    assert status["asset_count"] == 11
    assert status["planning_count"] == 1
    assert status["latest_planning_import"]["original_filename"].startswith(
        "DEMO__"
    )
    assert "import_real_data" in status["available_actions"]


def test_legacy_analysis_derived_from_demo_keeps_demo_state():
    assert client.post("/api/demo/v1/load").status_code == 200

    analysis = client.post(
        "/api/operations/analyze",
        json={"reserve_threshold": 1},
    )

    assert analysis.status_code == 200
    assert _count("analyses") == 1
    assert get_workspace_status().workspace_state is WorkspaceState.DEMO


def test_status_production_does_not_depend_on_filename():
    save_import(
        "planning",
        "DEMO__misleading-name.csv",
        None,
        [],
        [{"row_number": 2, "route": "TASK-001"}],
    )

    status = get_workspace_status()

    assert status.workspace_state is WorkspaceState.PRODUCTION
    assert status.is_demo is False
    assert status.task_count == 1


def test_status_production_exposes_latest_imports_and_counts():
    planning, asset = _production_workspace()

    payload = client.get(f"{BASE_URL}/status").json()

    assert payload["workspace_state"] == "PRODUCTION"
    assert payload["latest_planning_import"]["rows_imported"] == 2
    assert payload["latest_fleet_import"]["rows_imported"] == 3
    assert payload["task_count"] == 2
    assert payload["asset_count"] == 3
    assert payload["planning_count"] == 1
    assert payload["last_operational_update"]
    assert planning.planning.id > 0
    assert asset.id > 0


def test_reset_empty_is_successful_and_idempotent():
    response = client.post(f"{BASE_URL}/reset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_state"] == "EMPTY"
    assert payload["idempotent"] is True
    assert payload["message_code"] == "workspace_already_empty"
    assert not any(payload["removed_counts"].values())


def test_reset_demo_removes_registry_and_delegated_demo_reset_is_compatible():
    assert client.post("/api/demo/v1/load").status_code == 200

    response = client.post("/api/demo/v1/reset")

    assert response.status_code == 200
    assert response.json()["removed"]["imports"] == 2
    assert _count("demo_workspaces") == 0
    assert client.get(f"{BASE_URL}/status").json()["workspace_state"] == "EMPTY"
    assert _count("workspace_reset_audits") == 1


def test_reset_production_removes_operational_roots_and_children():
    _production_workspace()
    save_analysis({"routes": 2}, [])

    response = client.post(f"{BASE_URL}/reset")

    assert response.status_code == 200
    removed = response.json()["removed_counts"]
    assert removed["imports"] == 2
    assert removed["plannings"] == 1
    assert removed["assignments"] == 2
    assert removed["planning_versions"] == 1
    assert removed["fleet_assets"] == 1
    assert removed["fleet_asset_documents"] == 1
    assert removed["fleet_asset_events"] == 2
    assert removed["analyses"] == 1
    assert all(
        _count(table) == 0
        for table in workspace_repository.OPERATIONAL_DELETE_ORDER
    )


def test_reset_removes_briefing_snapshot_events_and_demo_data():
    loaded = client.post("/api/demo/v1/load")
    planning_id = loaded.json()["summary"]["planning_id"]
    briefing = client.post(
        "/api/briefing/v1/daily/generate",
        json={"planning_id": planning_id},
    )
    assert briefing.status_code == 200

    response = client.post(f"{BASE_URL}/reset")

    removed = response.json()["removed_counts"]
    assert removed["daily_briefings"] == 1
    assert removed["operation_snapshots"] == 1
    assert removed["planning_events"] >= 1
    assert removed["fleet_asset_documents"] == 2
    assert removed["demo_workspaces"] == 1
    assert response.json()["workspace_state"] == "EMPTY"


def test_configuration_versions_nomenclature_and_policy_are_preserved():
    _configuration_version()
    _production_workspace()
    before = _count("configuration_versions")

    reset = client.post(f"{BASE_URL}/reset")

    assert reset.status_code == 200
    assert _count("configuration_versions") == before == 1
    with db_session() as conn:
        row = conn.execute(
            "SELECT sections FROM configuration_versions"
        ).fetchone()
    sections = json.loads(row["sections"])
    assert any(item["key"] == "nomenclature" for item in sections)
    assert any(item["key"] == "reserve_policy" for item in sections)


def test_reset_audit_records_actor_states_counts_and_outcome():
    _production_workspace()

    response = client.post(f"{BASE_URL}/reset")
    payload = response.json()
    audit = workspace_repository.get_reset_audit(payload["reset_id"])

    assert audit["actor"] == "system/private-beta"
    assert audit["previous_state"] == "PRODUCTION"
    assert audit["final_state"] == "EMPTY"
    assert audit["outcome"] == "completed"
    assert audit["completed_at"]
    assert audit["removed_counts"]["imports"] == 2
    assert audit["sanitized_error"] is None


def test_second_reset_is_audited_and_returns_all_zero_counts():
    _production_workspace()
    first = client.post(f"{BASE_URL}/reset")
    second = client.post(f"{BASE_URL}/reset")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert not any(second.json()["removed_counts"].values())
    assert _count("workspace_reset_audits") == 2


def test_reset_rolls_back_all_deletions_on_failure(monkeypatch):
    _production_workspace()
    original = workspace_repository.reset_operational_data

    def fail_after_delete(conn):
        original(conn)
        raise RuntimeError("Synthetic transactional failure")

    monkeypatch.setattr(
        workspace_repository,
        "reset_operational_data",
        fail_after_delete,
    )

    response = client.post(f"{BASE_URL}/reset")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "WORKSPACE_RESET_FAILED"
    assert _count("imports") == 2
    assert _count("plannings") == 1
    assert _count("fleet_assets") == 1
    with db_session() as conn:
        audit = conn.execute(
            """
            SELECT outcome, sanitized_error
            FROM workspace_reset_audits
            """
        ).fetchone()
    assert audit["outcome"] == "failed"
    assert audit["sanitized_error"] == "workspace_reset_failed"


def test_concurrent_reset_is_rejected_by_backend_lock():
    assert reset_service._RESET_LOCK.acquire(blocking=False)
    try:
        response = client.post(f"{BASE_URL}/reset")
    finally:
        reset_service._RESET_LOCK.release()

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "WORKSPACE_RESET_IN_PROGRESS"


def test_real_import_and_asset_creation_are_blocked_in_demo():
    assert client.post("/api/demo/v1/load").status_code == 200

    imported = client.post(
        "/api/imports/planning",
        files={
            "file": (
                "real.csv",
                b"route,driver\nR1,Driver 1\n",
                "text/csv",
            )
        },
    )
    asset = client.post(
        "/api/plugins/fleet/v1/assets",
        json={
            "external_identifier": "real-asset",
            "status": "active",
            "availability": "available",
            "capabilities": [],
        },
    )

    assert imported.status_code == 409
    assert imported.json()["detail"]["code"] == (
        "DEMO_WORKSPACE_RESET_REQUIRED"
    )
    assert asset.status_code == 409
    assert asset.json()["detail"]["code"] == (
        "DEMO_WORKSPACE_RESET_REQUIRED"
    )
    assert get_workspace_status().workspace_state is WorkspaceState.DEMO


def test_demo_load_is_blocked_in_production_without_changing_data():
    import_ids = _production_imports()

    response = client.post("/api/demo/v1/load")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DEMO_WORKSPACE_NOT_EMPTY"
    assert _count("imports") == 2
    assert import_ids[0] > 0
    assert _count("demo_workspaces") == 0


def test_no_operational_orphans_remain_after_reset():
    _production_workspace()

    assert client.post(f"{BASE_URL}/reset").status_code == 200

    with db_session() as conn:
        checks = (
            """
            SELECT COUNT(*) AS total
            FROM assignments
            WHERE planning_id NOT IN (SELECT id FROM plannings)
            """,
            """
            SELECT COUNT(*) AS total
            FROM fleet_asset_events
            WHERE asset_id NOT IN (SELECT id FROM fleet_assets)
            """,
            """
            SELECT COUNT(*) AS total
            FROM fleet_asset_documents
            WHERE asset_id NOT IN (SELECT id FROM fleet_assets)
            """,
        )
        assert all(
            int(conn.execute(statement).fetchone()["total"]) == 0
            for statement in checks
        )


def test_workspace_schema_and_queries_use_postgres_compatibility_layer(
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

    monkeypatch.setattr(workspace_repository, "db_session", fake_session)
    workspace_repository.init_schema()
    workspace_repository.start_reset_audit(
        reset_id="reset-postgres-test",
        started_at="2026-07-20T00:00:00Z",
        actor="test",
        previous_state="EMPTY",
    )

    statements = [
        statement
        for statement, _ in raw.cursor_instance.statements
    ]
    assert any(
        "CREATE TABLE IF NOT EXISTS workspace_reset_audits" in statement
        for statement in statements
    )
    insert = next(
        statement
        for statement in statements
        if "INSERT INTO workspace_reset_audits" in statement
    )
    assert "%s" in insert
    assert "AUTOINCREMENT" not in "\n".join(statements)


def test_workspace_contract_is_typed_in_openapi():
    schema = app.openapi()
    status = schema["paths"][f"{BASE_URL}/status"]["get"]
    reset = schema["paths"][f"{BASE_URL}/reset"]["post"]

    assert status["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/WorkspaceStatusResponse")
    assert reset["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/WorkspaceResetResponse")
    components = schema["components"]["schemas"]
    assert set(components["WorkspaceState"]["enum"]) == {
        "EMPTY",
        "DEMO",
        "PRODUCTION",
    }


def test_preexisting_openapi_paths_are_byte_compatible():
    paths = app.openapi()["paths"]
    added_paths = {
        path
        for path in paths
        if path.startswith("/api/workspace/")
        or path == "/api/runtime/authority"
        or path == "/api/runtime/execution-intent"
        or path.startswith("/api/plugins/workforce/")
        or path.startswith("/api/planning/drafts")
        or path.startswith("/api/planning/confirmation")
        or path.startswith("/api/planning/publication")
        or path
        in {
            "/api/planning/readiness",
            "/api/planning/conflicts",
            "/api/planning/timeline",
            "/api/plugins/fleet/v1/sync/preview",
            "/api/plugins/fleet/v1/sync/confirm",
            "/api/plugins/fleet/v1/sync/latest",
            "/api/plugins/fleet/v1/availability",
        }
    }
    existing = {
        path: value
        for path, value in paths.items()
        if path not in added_paths
    }
    digest = hashlib.sha256(
        json.dumps(
            existing,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert digest == PRE_WORKSPACE_PATHS_SHA256
    assert set(paths) - set(existing) == added_paths


def test_workspace_domain_contains_no_market_specific_vocabulary():
    workspace_dir = Path(__file__).parents[1] / "app" / "workspace"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in workspace_dir.glob("*.py")
    ).casefold()

    assert "amazon" not in source
    assert "app.adapters" not in source
    assert "app.plugins" not in source


def test_operational_and_preserved_table_classification_is_complete():
    assert workspace_repository.OPERATIONAL_DELETE_ORDER == (
        "planning_publications",
        "planning_confirmations",
        "planning_draft_changes",
        "planning_draft_versions",
        "planning_drafts",
        "daily_briefings",
        "planning_events",
        "planning_versions",
        "assignments",
        "plannings",
        "operation_snapshots",
        "analyses",
        "workforce_changes",
        "workforce_day_statuses",
        "workforce_requirements",
        "workforce_members",
        "workforce_imports",
        "fleet_asset_documents",
        "fleet_sync_event_fingerprints",
        "fleet_asset_events",
        "fleet_sync_runs",
        "fleet_asset_metadata",
        "fleet_assets",
        "imports",
        "demo_workspaces",
    )
    assert workspace_repository.PRESERVED_TABLES == (
        "configuration_versions",
        "workspace_reset_audits",
    )
    assert DEMO_WORKSPACE_ID
