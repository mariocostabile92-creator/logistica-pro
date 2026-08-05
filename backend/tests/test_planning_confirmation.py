import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.tenant_context import bind_organization, reset_organization
from app.api.dependencies.planning_confirmation import (
    get_planning_confirmation_runtime,
)
from app.domain.planning_confirmation import (
    PlanningConfirmationState,
)
from app.domain.planning_readiness import (
    PlanningReadinessBlocker,
    PlanningReadinessSeverity,
    PlanningReadinessStatus,
)
from app.main import app
from app.repositories.planning_confirmation_repository import (
    SqlPlanningConfirmationRepository,
)
from app.workspace.reset_service import reset_workspace
from planning_confirmation_helpers import (
    NOW,
    OPERATION_DATE,
    ORGANIZATION_ID,
    SCOPE,
    UNIT,
    confirmation_context,
    confirmation_runtime,
    confirmation_service,
    create_draft,
    draft_service,
)


APP_DIR = Path(__file__).parents[1] / "app"


def test_confirmation_states_are_complete_and_models_are_immutable():
    assert {state.value for state in PlanningConfirmationState} == {
        "NOT_READY",
        "READY_TO_CONFIRM",
        "CONFIRMED",
        "REJECTED",
        "ERROR",
    }
    service = confirmation_service()
    draft = create_draft(draft_service())
    report = service.confirm(
        context=confirmation_context(draft),
        actor="qa-operator",
    )

    with pytest.raises(ValidationError):
        report.current.actor = "changed"


def test_saved_ready_draft_passes_every_explainable_rule():
    draft = create_draft(draft_service())
    result = confirmation_service().validate(confirmation_context(draft))

    assert result.state is PlanningConfirmationState.READY_TO_CONFIRM
    assert result.can_confirm is True
    assert len(result.rules) == 8
    assert all(rule.passed for rule in result.rules)
    assert all(rule.code and rule.reason and rule.remediation_hint for rule in result.rules)


@pytest.mark.parametrize(
    ("case", "expected_code"),
    (
        ("missing-draft", "DRAFT_PRESENT"),
        ("dirty-draft", "DRAFT_SAVED"),
        ("readiness", "READINESS_READY"),
        ("blocker", "NO_CRITICAL_BLOCKERS"),
        ("runtime", "RUNTIME_COMPATIBLE"),
        ("envelope", "ENVELOPE_VALID"),
        ("version", "DRAFT_VERSION_COHERENT"),
    ),
)
def test_validation_rejects_every_blocking_precondition(case, expected_code):
    drafts = draft_service()
    draft = None if case == "missing-draft" else create_draft(
        drafts,
        saved=case != "dirty-draft",
    )
    context = confirmation_context(draft)
    if case == "readiness":
        context = context.model_copy(update={
            "readiness": context.readiness.model_copy(update={
                "status": PlanningReadinessStatus.BLOCKED,
                "is_ready": False,
            }),
        })
    if case == "blocker":
        blocker = PlanningReadinessBlocker(
            code="QA_BLOCKER",
            category="validation",
            message="Blocker sintetico.",
            rationale="Copertura regola Confirmation.",
            source="qa",
            severity=PlanningReadinessSeverity.CRITICAL,
            remediation_hint="Risolvi il blocker sintetico.",
        )
        context = context.model_copy(update={
            "readiness": context.readiness.model_copy(
                update={"blockers": (blocker,)}
            ),
        })
    if case == "runtime":
        context = context.model_copy(update={
            "runtime_status": "incompatible",
            "runtime_compatible": False,
        })
    if case == "envelope":
        context = context.model_copy(update={"envelope": None})
    if case == "version":
        context = context.model_copy(update={
            "requested_draft_version": draft.version.number + 1,
        })

    result = confirmation_service().validate(context)

    failed = {rule.code for rule in result.rules if not rule.passed}
    assert result.state is PlanningConfirmationState.NOT_READY
    assert result.can_confirm is False
    assert expected_code in failed


def test_confirmation_persists_identity_scope_actor_version_and_fingerprint():
    drafts = draft_service()
    draft = create_draft(drafts)
    before = draft.model_dump()
    service = confirmation_service()
    report = service.confirm(
        context=confirmation_context(draft),
        actor="qa-operator",
    )

    confirmed = report.current
    assert report.state is PlanningConfirmationState.CONFIRMED
    assert confirmed.actor == "qa-operator"
    assert confirmed.scope.operational_unit == UNIT
    assert confirmed.version == 1
    assert confirmed.draft_version == draft.version.number
    assert len(confirmed.fingerprint) == 64
    assert confirmed.fingerprint == service.get_current(SCOPE).fingerprint
    assert service.history(SCOPE).total == 1
    assert drafts.current(draft.scope).draft.model_dump() == before


def test_double_confirmation_is_rejected_without_overwriting_history():
    draft = create_draft(draft_service())
    service = confirmation_service()
    first = service.confirm(
        context=confirmation_context(draft),
        actor="qa-operator",
    )
    second = service.confirm(
        context=confirmation_context(draft, service=service),
        actor="second-operator",
    )

    assert first.state is PlanningConfirmationState.CONFIRMED
    assert second.state is PlanningConfirmationState.REJECTED
    assert second.current.confirmation_id == first.current.confirmation_id
    assert second.history.total == 1
    assert service.history(SCOPE).confirmations[0].actor == "qa-operator"


def test_runtime_and_api_support_current_validate_confirm_and_history():
    runtime, draft = confirmation_runtime()
    app.dependency_overrides[get_planning_confirmation_runtime] = lambda: runtime
    client = TestClient(app)
    query = {
        "organization_id": ORGANIZATION_ID,
        "operational_unit_id": UNIT.external_identifier,
        "planning_date": OPERATION_DATE.isoformat(),
    }
    payload = {
        **query,
        "draft_id": draft.draft_id,
        "draft_version": draft.version.number,
    }
    try:
        current = client.get("/api/planning/confirmation/current", params=query)
        validated = client.post(
            "/api/planning/confirmation/validate",
            json=payload,
        )
        confirmed = client.post(
            "/api/planning/confirmation/confirm",
            json=payload,
        )
        history = client.get("/api/planning/confirmation/history", params=query)
        duplicate = client.post(
            "/api/planning/confirmation/confirm",
            json=payload,
        )
    finally:
        app.dependency_overrides.clear()

    assert current.status_code == 200
    assert current.json()["state"] == "READY_TO_CONFIRM"
    assert validated.json()["result"]["can_confirm"] is True
    assert confirmed.json()["state"] == "CONFIRMED"
    assert history.json()["total"] == 1
    assert duplicate.json()["state"] == "REJECTED"
    assert len(confirmed.content) < 12_000
    assert "human_resources" not in confirmed.text
    assert "assets" not in confirmed.text


def test_workspace_reset_removes_confirmations_before_drafts():
    drafts = draft_service()
    draft = create_draft(drafts)
    service = confirmation_service()
    service.confirm(
        context=confirmation_context(draft),
        actor="qa-operator",
    )

    token = bind_organization(SCOPE.organization_id)
    try:
        reset_workspace(actor="qa")
    finally:
        reset_organization(token)

    assert SqlPlanningConfirmationRepository().get_history(SCOPE).total == 0


def test_openapi_exposes_only_the_four_confirmation_operations():
    paths = app.openapi()["paths"]

    assert set(paths["/api/planning/confirmation/current"]) == {"get"}
    assert set(paths["/api/planning/confirmation/validate"]) == {"post"}
    assert set(paths["/api/planning/confirmation/confirm"]) == {"post"}
    assert set(paths["/api/planning/confirmation/history"]) == {"get"}


def test_confirmation_domain_has_no_infrastructure_or_legacy_dependency():
    forbidden = {
        "app.api",
        "app.repositories",
        "app.runtime",
        "app.legacy",
        "app.services",
    }
    for path in (APP_DIR / "domain" / "planning_confirmation").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not any(
            module == prefix or module.startswith(f"{prefix}.")
            for module in imports
            for prefix in forbidden
        )
