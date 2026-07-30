import ast
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.briefing.models import BriefingSeverity
from app.briefing.prioritization import priority_score
from app.core.database import (
    _postgres_schema_statement,
    _postgres_statement,
    db_session,
)
from app.main import app
from app.schemas.planning_schema import GeneratePlanningRequest
from app.services.planning_generation_service import (
    generate_planning,
    get_planning_bundle,
)
from tests.planning_helpers import save_normalized_imports, simple_rows


client = TestClient(app)
BASE_URL = "/api/briefing/v1/daily"
APP_DIR = Path(__file__).parents[1] / "app"
PROJECT_DIR = Path(__file__).parents[2]
PRE_BRIEFING_PATHS_SHA256 = (
    "f29fbaf22add666f5cd48cb599a6f870cc6bca80351bdc2e55a2c458dcf03338"
)


def _generate_planning(
    *,
    tasks: int = 1,
    human_resources: int = 2,
    assets: int = 2,
):
    planning_rows, fleet_rows = simple_rows(
        routes=tasks,
        drivers=human_resources,
        vehicles=assets,
    )
    planning_import_id, fleet_import_id = save_normalized_imports(
        planning_rows,
        fleet_rows,
    )
    return generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_import_id,
            fleet_import_id=fleet_import_id,
            operation_date="2026-07-20",
        )
    )


def _generate_briefing(planning_id: int | None = None):
    payload = {"planning_id": planning_id} if planning_id else {}
    response = client.post(f"{BASE_URL}/generate", json=payload)
    assert response.status_code == 200
    return response.json()


def _count(table: str) -> int:
    allowed = {
        "assignments",
        "daily_briefings",
        "fleet_assets",
        "imports",
        "plannings",
    }
    assert table in allowed
    with db_session() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS total FROM {table}"
        ).fetchone()
    return int(row["total"])


def test_empty_database_returns_typed_unavailable_without_expected_error():
    latest = client.get(f"{BASE_URL}/latest")
    generated = client.post(f"{BASE_URL}/generate", json={})

    assert latest.status_code == 200
    assert generated.status_code == 200
    assert latest.json()["status"] == "unavailable"
    assert latest.json()["attention_level"] == "unavailable"
    assert latest.json()["executive_summary"] == (
        "Il briefing sarà disponibile dopo la creazione del primo planning."
    )
    assert latest.json() == generated.json()
    assert _count("daily_briefings") == 0


def test_latest_is_typed_unavailable_until_current_sources_are_generated():
    planning = _generate_planning()

    response = client.get(f"{BASE_URL}/latest")

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["planning_id"] == planning.planning.id
    assert "non è ancora stato generato" in response.json()["executive_summary"]


def test_valid_planning_generates_versioned_typed_payload():
    planning = _generate_planning()

    briefing = _generate_briefing(planning.planning.id)

    assert briefing["status"] == "available"
    assert briefing["contract_version"] == "1.0"
    assert briefing["briefing_id"].startswith("briefing-")
    assert len(briefing["fingerprint"]) == 64
    assert briefing["briefing_revision"] == 1
    assert briefing["planning_id"] == planning.planning.id
    assert briefing["planning_version"] == 1
    assert briefing["configuration_version"] == 0
    assert briefing["source_references"]


def test_stable_attention_level_and_summary_follow_sources():
    _generate_planning(tasks=1, human_resources=2, assets=2)

    briefing = _generate_briefing()

    assert briefing["attention_level"] == "stable"
    assert "non presenta condizioni bloccanti" in (
        briefing["executive_summary"]
    )
    assert briefing["capacity_snapshot"]["margin"] == 1


def test_attention_level_detects_low_reserve_margin():
    _generate_planning(tasks=2, human_resources=2, assets=2)

    briefing = _generate_briefing()

    assert briefing["attention_level"] == "attention"
    assert briefing["capacity_snapshot"]["margin"] == 0
    assert any(
        item["issue_code"] == "RESERVE_MARGIN_LOW"
        and item["severity"] == "high"
        for item in briefing["sections"]
    )


def test_critical_level_ranks_uncovered_task_before_other_items():
    _generate_planning(tasks=2, human_resources=2, assets=1)

    briefing = _generate_briefing()

    assert briefing["attention_level"] == "critical"
    assert briefing["metrics"]["critical_items"] >= 1
    assert briefing["sections"][0]["severity"] == "blocker"
    assert briefing["sections"][0]["issue_code"] in {
        "CAPACITY_SHORTAGE",
        "TASK_UNCOVERED",
    }
    assert "Task non coperti" in briefing["attention_reason"]
    assert "margine Capacity" not in briefing["attention_reason"]


def test_priority_rules_are_explicit_and_deterministic():
    first = priority_score(BriefingSeverity.HIGH, 3, 2)
    repeated = priority_score(BriefingSeverity.HIGH, 3, 2)

    assert first == repeated == 432
    assert priority_score(BriefingSeverity.BLOCKER, 1, 1) > first
    assert priority_score(BriefingSeverity.CRITICAL, 4, 4) > (
        priority_score(BriefingSeverity.HIGH, 4, 4)
    )


def test_every_claim_and_recommendation_has_verifiable_sources():
    _generate_planning(tasks=2, human_resources=2, assets=2)

    briefing = _generate_briefing()

    assert {
        item["source_type"]
        for item in briefing["source_references"]
    }.issuperset({"planning", "capacity", "configuration"})
    for section in briefing["sections"]:
        assert section["source_references"]
        assert section["ranking_explanation"]
        assert section["rationale"]
        for fact in section["facts"]:
            assert fact["source_type"]
            assert fact["source_id"]
            assert fact["provenance"] in {
                "observed",
                "configured",
                "derived",
                "suggestion",
                "limitation",
            }
        if section["recommendation"]:
            recommendation = section["recommendation"]
            assert recommendation["data_used"]
            assert recommendation["reason"]
            assert recommendation["expected_impact"]
            assert recommendation["requires_human_confirmation"] is True


def test_generation_is_idempotent_for_unchanged_sources():
    planning = _generate_planning(tasks=2, human_resources=2, assets=2)

    first = _generate_briefing(planning.planning.id)
    second = _generate_briefing(planning.planning.id)
    latest = client.get(f"{BASE_URL}/latest").json()

    assert first == second == latest
    assert _count("daily_briefings") == 1


def test_source_change_creates_new_revision_and_preserves_previous():
    planning = _generate_planning(tasks=1, human_resources=2, assets=2)
    first = _generate_briefing(planning.planning.id)
    assignment_id = planning.assignments[0].id

    updated = client.patch(
        f"/api/planning/assignments/{assignment_id}",
        json={"notes": "Synthetic review", "confirm": True},
    )
    assert updated.status_code == 200
    second = _generate_briefing(planning.planning.id)

    assert second["briefing_revision"] == 2
    assert second["briefing_id"] != first["briefing_id"]
    assert second["fingerprint"] != first["fingerprint"]
    assert _count("daily_briefings") == 2


def test_briefing_does_not_modify_operational_records():
    planning = _generate_planning(tasks=2, human_resources=3, assets=3)
    before = get_planning_bundle(planning.planning.id).model_dump(mode="json")
    counts_before = {
        table: _count(table)
        for table in ("imports", "plannings", "assignments", "fleet_assets")
    }

    _generate_briefing(planning.planning.id)

    after = get_planning_bundle(planning.planning.id).model_dump(mode="json")
    assert after == before
    assert {
        table: _count(table) for table in counts_before
    } == counts_before


def test_sqlite_schema_and_postgres_translation_support_briefing_table():
    with db_session() as conn:
        columns = conn.execute(
            "PRAGMA table_info(daily_briefings)"
        ).fetchall()

    assert {
        row["name"] for row in columns
    }.issuperset(
        {
            "briefing_id",
            "fingerprint",
            "planning_id",
            "planning_version",
            "configuration_version",
            "contract_version",
            "briefing_revision",
            "payload",
            "is_demo",
        }
    )
    statement, returns_identity = _postgres_statement(
        "INSERT INTO daily_briefings (briefing_id) VALUES (?)"
    )
    assert returns_identity is True
    assert statement.endswith("RETURNING id")
    assert "VALUES (%s)" in statement
    assert "SERIAL PRIMARY KEY" in _postgres_schema_statement(
        "id INTEGER PRIMARY KEY AUTOINCREMENT"
    )


def test_demo_workspace_produces_expected_real_briefing_and_reset_removes_it():
    loaded = client.post("/api/demo/v1/load")
    assert loaded.status_code == 200

    briefing = _generate_briefing(
        loaded.json()["summary"]["planning_id"]
    )

    assert briefing["is_demo"] is True
    assert briefing["attention_level"] == "attention"
    assert briefing["readiness_snapshot"]["level"] == "yellow"
    assert briefing["capacity_snapshot"]["margin"] == 0
    assert briefing["planning_id"]
    assert not any(
        item["issue_code"] == "TASK_UNCOVERED"
        for item in briefing["sections"]
    )
    assert any(
        item["issue_code"] == "HUMAN_RESOURCE_SUBSTITUTED"
        for item in briefing["sections"]
    )
    assert any(
        item["issue_code"] == "PLANNING_ALTERNATIVES_AVAILABLE"
        for item in briefing["sections"]
    )
    operational_unit_issues = [
        item
        for item in briefing["sections"]
        if item["issue_code"] == "OPERATIONAL_UNIT_UNRECOGNIZED"
    ]
    assert len(operational_unit_issues) == 1
    assert len(operational_unit_issues[0]["source_references"]) == 10

    reset = client.post("/api/demo/v1/reset")
    assert reset.status_code == 200
    assert _count("daily_briefings") == 0
    latest = client.get(f"{BASE_URL}/latest")
    assert latest.status_code == 200
    assert latest.json()["status"] == "unavailable"


def test_demo_load_is_blocked_when_a_real_briefing_exists():
    real_planning = _generate_planning()
    real_briefing = _generate_briefing(real_planning.planning.id)
    loaded = client.post("/api/demo/v1/load")
    assert loaded.status_code == 409

    latest = client.get(f"{BASE_URL}/latest").json()
    assert latest["briefing_id"] == real_briefing["briefing_id"]
    assert latest["is_demo"] is False
    assert _count("daily_briefings") == 1


def test_new_domain_has_no_vertical_or_ai_provider_dependency():
    briefing_dir = APP_DIR / "briefing"
    forbidden_imports = (
        "app.adapters",
        "app.demo",
        "openai",
        "anthropic",
        "boto3",
    )
    violations = []
    for path in briefing_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "amazon" not in source.casefold()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_imports):
                        violations.append(f"{path.name}: {alias.name}")
            if module and module.startswith(forbidden_imports):
                violations.append(f"{path.name}: {module}")
    assert violations == []
    requirements = (
        PROJECT_DIR / "backend" / "requirements.txt"
    ).read_text(encoding="utf-8").casefold()
    assert not {
        item
        for item in ("openai", "anthropic", "bedrock", "vertex")
        if item in requirements
    }


def test_openapi_preserves_existing_paths_and_adds_only_two_briefing_routes():
    paths = app.openapi()["paths"]
    existing_paths = {
        path: value
        for path, value in paths.items()
        if (
                        not path.startswith("/api/briefing/")
                        and not path.startswith("/api/fleet/damage")
                        and not path.startswith("/api/fleet/maintenances")
                        and not path.startswith("/api/fleet/documents")
                        and not path.startswith("/api/fleet/franchises")
                        and not path.startswith("/api/fleet/insurance-policies")
                        and not path.startswith("/api/fleet/vehicles/")
                    and not path.startswith("/api/plugins/fleet/v1/journal/")
                    and not path.endswith("/profile")
            and path != "/api/runtime/authority"
            and path != "/api/runtime/execution-intent"
            and path != "/api/runtime/execution-attempt"
            and path != "/api/runtime/shadow"
                and path != "/api/runtime/output"
                and path != "/api/runtime/canary"
                and path != "/api/runtime/primary"
                and path != "/api/runtime/legacy-retirement"
                and not path.startswith("/api/workspace/")
            and not path.startswith("/api/plugins/workforce/")
            and not path.startswith("/api/planning/drafts")
            and not path.startswith("/api/planning/confirmation")
            and not path.startswith("/api/planning/publication")
            and path not in {
                "/api/planning/readiness",
                "/api/planning/conflicts",
                "/api/planning/timeline",
                "/api/plugins/fleet/v1/sync/preview",
                "/api/plugins/fleet/v1/sync/confirm",
                "/api/plugins/fleet/v1/sync/latest",
                "/api/plugins/fleet/v1/availability",
            }
        )
    }
    digest = hashlib.sha256(
        json.dumps(
            existing_paths,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert digest == PRE_BRIEFING_PATHS_SHA256
    assert {
        path
        for path in paths
        if path.startswith("/api/briefing/")
    } == {
        "/api/briefing/v1/daily/latest",
        "/api/briefing/v1/daily/generate",
    }
    assert "get" in paths["/api/briefing/v1/daily/latest"]
    assert "post" in paths["/api/briefing/v1/daily/generate"]
    assert (
        paths["/api/briefing/v1/daily/latest"]["get"]["responses"]["200"]
        ["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/DailyOperationsBriefing"
    )
