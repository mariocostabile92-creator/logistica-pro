import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.tenant_context import bind_organization, reset_organization
from app.api.dependencies.planning_publication import (
    get_planning_publication_runtime,
)
from app.domain.planning_confirmation import PlanningConfirmationState
from app.domain.planning_publication import PlanningPublicationState
from app.main import app
from app.repositories.planning_publication_repository import (
    SqlPlanningPublicationRepository,
)
from app.workspace.reset_service import reset_workspace
from planning_confirmation_helpers import OPERATION_DATE, ORGANIZATION_ID, UNIT
from planning_publication_helpers import (
    PUBLICATION_SCOPE,
    create_confirmation,
    publication_context,
    publication_runtime,
    publication_service,
)


APP_DIR = Path(__file__).parents[1] / "app"


def test_publication_states_are_complete_and_models_are_immutable():
    assert {state.value for state in PlanningPublicationState} == {
        "NOT_PUBLISHED",
        "READY_TO_PUBLISH",
        "PUBLISHED",
        "FAILED",
        "ERROR",
    }
    confirmation = create_confirmation()
    report = publication_service().publish(
        context=publication_context(confirmation),
        actor="qa-publisher",
    )

    with pytest.raises(ValidationError):
        report.current.actor = "changed"


def test_valid_confirmation_passes_every_explainable_rule():
    confirmation = create_confirmation()
    result = publication_service().validate(
        publication_context(confirmation)
    )

    assert result.state is PlanningPublicationState.READY_TO_PUBLISH
    assert result.can_publish is True
    assert len(result.rules) == 7
    assert all(rule.passed for rule in result.rules)
    assert all(
        rule.code and rule.reason and rule.remediation_hint
        for rule in result.rules
    )


@pytest.mark.parametrize(
    ("case", "expected_code"),
    (
        ("missing-confirmation", "CONFIRMED_PLAN_PRESENT"),
        ("invalid-confirmation", "CONFIRMATION_VALID"),
        ("runtime", "RUNTIME_COMPATIBLE"),
        ("fingerprint", "FINGERPRINT_COHERENT"),
        ("version", "VERSION_COHERENT"),
        ("operational-unit", "OPERATIONAL_UNIT_VALID"),
    ),
)
def test_validation_rejects_every_blocking_precondition(case, expected_code):
    confirmation = (
        None if case == "missing-confirmation" else create_confirmation()
    )
    context = publication_context(
        confirmation,
        runtime_compatible=case != "runtime",
        operational_unit_valid=case != "operational-unit",
    )
    if case == "invalid-confirmation":
        invalid_validation = confirmation.validation.model_copy(
            update={
                "state": PlanningConfirmationState.NOT_READY,
                "can_confirm": False,
            }
        )
        context = context.model_copy(
            update={
                "confirmation": confirmation.model_copy(
                    update={"validation": invalid_validation}
                )
            }
        )
    if case == "fingerprint":
        context = context.model_copy(
            update={"requested_confirmation_fingerprint": "0" * 64}
        )
    if case == "version":
        context = context.model_copy(
            update={
                "requested_confirmation_version": confirmation.version + 1
            }
        )

    result = publication_service().validate(context)

    failed = {rule.code for rule in result.rules if not rule.passed}
    assert result.state is PlanningPublicationState.NOT_PUBLISHED
    assert result.can_publish is False
    assert expected_code in failed


def test_publication_persists_contract_without_mutating_confirmation():
    confirmation = create_confirmation()
    before = confirmation.model_dump()
    service = publication_service()
    report = service.publish(
        context=publication_context(confirmation),
        actor="qa-publisher",
    )

    published = report.current
    assert report.state is PlanningPublicationState.PUBLISHED
    assert published.actor == "qa-publisher"
    assert published.scope.operational_unit == UNIT
    assert published.version == 1
    assert published.confirmation_id == confirmation.confirmation_id
    assert published.confirmation_version == confirmation.version
    assert published.confirmation_fingerprint == confirmation.fingerprint
    assert len(published.fingerprint) == 64
    assert service.get_current(PUBLICATION_SCOPE) == published
    assert service.history(PUBLICATION_SCOPE).total == 1
    assert confirmation.model_dump() == before


def test_double_publication_fails_without_overwriting_history():
    confirmation = create_confirmation()
    service = publication_service()
    first = service.publish(
        context=publication_context(confirmation),
        actor="qa-publisher",
    )
    second = service.publish(
        context=publication_context(confirmation, service=service),
        actor="second-publisher",
    )

    assert first.state is PlanningPublicationState.PUBLISHED
    assert second.state is PlanningPublicationState.FAILED
    assert second.current.publication_id == first.current.publication_id
    assert second.history.total == 1
    assert service.history(PUBLICATION_SCOPE).publications[0].actor == (
        "qa-publisher"
    )


def test_runtime_and_api_support_current_validate_publish_and_history():
    runtime, confirmation = publication_runtime()
    app.dependency_overrides[get_planning_publication_runtime] = lambda: runtime
    client = TestClient(app)
    query = {
        "organization_id": ORGANIZATION_ID,
        "operational_unit_id": UNIT.external_identifier,
        "planning_date": OPERATION_DATE.isoformat(),
    }
    payload = {
        **query,
        "operational_unit_name": UNIT.name,
        "confirmation_id": confirmation.confirmation_id,
        "confirmation_version": confirmation.version,
        "confirmation_fingerprint": confirmation.fingerprint,
    }
    try:
        current = client.get("/api/planning/publication/current", params=query)
        validated = client.post(
            "/api/planning/publication/validate",
            json=payload,
        )
        published = client.post(
            "/api/planning/publication/publish",
            json=payload,
        )
        history = client.get("/api/planning/publication/history", params=query)
        duplicate = client.post(
            "/api/planning/publication/publish",
            json=payload,
        )
    finally:
        app.dependency_overrides.clear()

    assert current.status_code == 200
    assert current.json()["state"] == "READY_TO_PUBLISH"
    assert validated.json()["result"]["can_publish"] is True
    assert published.json()["state"] == "PUBLISHED"
    assert history.json()["total"] == 1
    assert duplicate.json()["state"] == "FAILED"
    assert len(published.content) < 10_000
    assert "human_resources" not in published.text
    assert "assets" not in published.text
    assert "assignments" not in published.text


def test_workspace_reset_removes_publications_before_confirmations():
    confirmation = create_confirmation()
    service = publication_service()
    service.publish(
        context=publication_context(confirmation),
        actor="qa-publisher",
    )

    token = bind_organization(PUBLICATION_SCOPE.organization_id)
    try:
        reset_workspace(actor="qa")
    finally:
        reset_organization(token)

    assert SqlPlanningPublicationRepository().get_history(
        PUBLICATION_SCOPE
    ).total == 0


def test_openapi_exposes_only_the_four_publication_operations():
    paths = app.openapi()["paths"]

    assert set(paths["/api/planning/publication/current"]) == {"get"}
    assert set(paths["/api/planning/publication/validate"]) == {"post"}
    assert set(paths["/api/planning/publication/publish"]) == {"post"}
    assert set(paths["/api/planning/publication/history"]) == {"get"}


def test_publication_domain_has_no_infrastructure_or_legacy_dependency():
    forbidden = {
        "app.api",
        "app.repositories",
        "app.runtime",
        "app.legacy",
        "app.services",
    }
    for path in (APP_DIR / "domain" / "planning_publication").glob("*.py"):
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
