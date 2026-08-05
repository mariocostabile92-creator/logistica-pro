import ast
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.core_language import OperationalUnit
from app.domain.planning_drafts import (
    PlanningDraftAlreadyExistsError,
    PlanningDraftInvalidStateError,
    PlanningDraftMetadata,
    PlanningDraftScope,
    PlanningDraftService,
    PlanningDraftState,
    PlanningDraftVersionConflictError,
)
from app.main import app
from app.auth.tenant_context import bind_organization, reset_organization
from app.repositories.planning_draft_repository import (
    SqlPlanningDraftRepository,
)
from app.workspace.reset_service import reset_workspace


NOW = datetime(2026, 7, 22, 7, 0, tzinfo=UTC)
OPERATION_DATE = date(2026, 7, 22)
UNIT = OperationalUnit(external_identifier="unit-a", name="Unit A")
SCOPE = PlanningDraftScope(
    organization_id="organization-one",
    operational_unit=UNIT,
    planning_date=OPERATION_DATE,
)
APP_DIR = Path(__file__).parents[1] / "app"


class AdvancingClock:
    def __init__(self):
        self._calls = 0

    def __call__(self):
        value = NOW + timedelta(minutes=self._calls)
        self._calls += 1
        return value


class Identifiers:
    def __init__(self):
        self._value = 0

    def __call__(self):
        self._value += 1
        return f"id-{self._value}"


def _service():
    return PlanningDraftService(
        repository=SqlPlanningDraftRepository(),
        clock=AdvancingClock(),
        identifier_factory=Identifiers(),
    )


def _create(service, *, name="Piano del mattino"):
    return service.create(
        scope=SCOPE,
        metadata=PlanningDraftMetadata(name=name, note="Prima proposta."),
        actor="tester",
    )


def test_draft_states_are_complete_and_models_are_immutable():
    assert {item.value for item in PlanningDraftState} == {
        "EMPTY",
        "CREATED",
        "DIRTY",
        "SAVED",
        "READ_ONLY",
        "ERROR",
    }
    draft = _create(_service()).draft

    assert draft is not None
    with pytest.raises(ValidationError):
        draft.state = PlanningDraftState.SAVED


def test_create_produces_version_snapshot_and_append_only_change():
    workspace = _create(_service())

    assert workspace.state is PlanningDraftState.CREATED
    assert workspace.draft.version.number == 1
    assert workspace.history.total_versions == 1
    assert workspace.history.total_changes == 1
    assert workspace.history.changes[0].change_type.value == "CREATED"


def test_only_one_active_draft_can_exist_for_a_scope():
    service = _service()
    _create(service)

    with pytest.raises(PlanningDraftAlreadyExistsError):
        _create(service, name="Secondo Draft")


def test_metadata_update_and_save_create_distinct_versions():
    service = _service()
    created = _create(service)
    dirty = service.update_metadata(
        draft_id=created.draft.draft_id,
        expected_version=1,
        changes={"name": "Piano aggiornato", "note": "Nota aggiornata."},
        actor="tester",
    )
    saved = service.save(
        draft_id=dirty.draft.draft_id,
        expected_version=2,
        actor="tester",
    )

    assert dirty.state is PlanningDraftState.DIRTY
    assert dirty.draft.version.number == 2
    assert saved.state is PlanningDraftState.SAVED
    assert saved.draft.version.number == 3
    assert saved.history.total_versions == 3
    assert [item.change_type.value for item in saved.history.changes] == [
        "SAVED",
        "METADATA_UPDATED",
        "CREATED",
    ]


def test_restore_creates_a_new_version_without_overwriting_history():
    service = _service()
    created = _create(service)
    dirty = service.update_metadata(
        draft_id=created.draft.draft_id,
        expected_version=1,
        changes={"name": "Nome temporaneo"},
        actor="tester",
    )
    saved = service.save(
        draft_id=dirty.draft.draft_id,
        expected_version=2,
        actor="tester",
    )
    restored = service.restore(
        draft_id=saved.draft.draft_id,
        expected_version=3,
        target_version=1,
        actor="tester",
    )

    assert restored.state is PlanningDraftState.SAVED
    assert restored.draft.version.number == 4
    assert restored.draft.version.restored_from_version == 1
    assert restored.draft.metadata.name == "Piano del mattino"
    assert [item.version.number for item in restored.history.snapshots] == [
        4,
        3,
        2,
        1,
    ]


def test_stale_versions_invalid_transitions_and_missing_drafts_are_rejected():
    service = _service()
    created = _create(service)

    with pytest.raises(PlanningDraftVersionConflictError):
        service.save(
            draft_id=created.draft.draft_id,
            expected_version=99,
            actor="tester",
        )
    saved = service.save(
        draft_id=created.draft.draft_id,
        expected_version=1,
        actor="tester",
    )
    with pytest.raises(PlanningDraftInvalidStateError):
        service.save(
            draft_id=saved.draft.draft_id,
            expected_version=2,
            actor="tester",
        )
    with pytest.raises(PlanningDraftInvalidStateError):
        service.restore(
            draft_id=saved.draft.draft_id,
            expected_version=2,
            target_version=2,
            actor="tester",
        )


def test_delete_is_logical_keeps_history_and_removes_the_active_draft():
    service = _service()
    created = _create(service)
    deleted = service.delete(
        draft_id=created.draft.draft_id,
        expected_version=1,
        actor="tester",
    )

    assert deleted.state is PlanningDraftState.READ_ONLY
    assert deleted.draft.deleted_at is not None
    assert deleted.history.changes[0].change_type.value == "DELETED"
    assert service.current(SCOPE).state is PlanningDraftState.EMPTY
    assert service.get_history(deleted.draft.draft_id).total_versions == 2


def test_draft_api_supports_the_full_non_operational_lifecycle():
    client = TestClient(app)
    scope = {
        "organization_id": "organization-api",
        "operational_unit_id": "unit-api",
        "planning_date": OPERATION_DATE.isoformat(),
    }
    empty = client.get("/api/planning/drafts/current", params=scope)
    created = client.post(
        "/api/planning/drafts",
        json={**scope, "name": "Draft API", "note": "Solo metadati."},
    )
    draft_id = created.json()["draft"]["draft_id"]
    dirty = client.patch(
        f"/api/planning/drafts/{draft_id}/metadata",
        json={"expected_version": 1, "name": "Draft API aggiornato"},
    )
    saved = client.post(
        f"/api/planning/drafts/{draft_id}/save",
        json={"expected_version": 2},
    )
    restored = client.post(
        f"/api/planning/drafts/{draft_id}/restore",
        json={"expected_version": 3, "target_version": 1},
    )
    history = client.get(f"/api/planning/drafts/{draft_id}/history")
    deleted = client.delete(
        f"/api/planning/drafts/{draft_id}",
        params={"expected_version": 4},
    )

    assert empty.status_code == 200
    assert empty.json()["state"] == "EMPTY"
    assert created.status_code == 201
    assert dirty.json()["state"] == "DIRTY"
    assert saved.json()["state"] == "SAVED"
    assert restored.json()["draft"]["metadata"]["name"] == "Draft API"
    assert history.json()["total_versions"] == 4
    assert deleted.json()["state"] == "READ_ONLY"
    assert "assignments" not in deleted.text
    assert "planning_id" not in deleted.text


def test_api_reports_typed_conflicts_and_payload_remains_compact():
    client = TestClient(app)
    payload = {
        "organization_id": "organization-conflict",
        "operational_unit_id": "unit-conflict",
        "planning_date": OPERATION_DATE.isoformat(),
        "name": "Draft",
    }
    created = client.post("/api/planning/drafts", json=payload)
    duplicate = client.post("/api/planning/drafts", json=payload)
    draft_id = created.json()["draft"]["draft_id"]
    stale = client.post(
        f"/api/planning/drafts/{draft_id}/save",
        json={"expected_version": 99},
    )

    assert len(created.content) < 15_000
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "PLANNING_DRAFT_ALREADY_EXISTS"
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "PLANNING_DRAFT_VERSION_CONFLICT"


def test_workspace_reset_removes_drafts_without_touching_legacy_planning():
    service = _service()
    _create(service)

    token = bind_organization(SCOPE.organization_id)
    try:
        result = reset_workspace()
    finally:
        reset_organization(token)

    assert result.idempotent is False
    assert service.current(SCOPE).state is PlanningDraftState.EMPTY


def test_openapi_exposes_typed_draft_routes_and_existing_planning_is_separate():
    paths = app.openapi()["paths"]

    assert set(paths["/api/planning/drafts/current"]) == {"get"}
    assert set(paths["/api/planning/drafts"]) == {"post"}
    assert set(paths["/api/planning/drafts/{draft_id}/metadata"]) == {"patch"}
    assert set(paths["/api/planning/drafts/{draft_id}/save"]) == {"post"}
    assert set(paths["/api/planning/drafts/{draft_id}/restore"]) == {"post"}
    assert set(paths["/api/planning/drafts/{draft_id}"]) == {"delete"}
    assert set(paths["/api/planning/drafts/{draft_id}/history"]) == {"get"}
    assert "/api/planning/generate" in paths


def test_draft_domain_has_no_database_repository_or_legacy_dependencies():
    forbidden = (
        "app.core.database",
        "app.repositories",
        "app.legacy",
        "app.services.planning",
    )
    violations = []
    for path in (APP_DIR / "domain" / "planning_drafts").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            violations.extend(
                f"{path.name}: {module}"
                for module in modules
                if module.startswith(forbidden)
            )

    assert violations == []
