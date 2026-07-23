from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.planning_runtime_output import (
    get_planning_runtime_output,
)
from app.core.database import db_session
from app.domain.core_language import (
    AssetReference,
    HumanResource,
    ResourceAvailability,
    ResourceKind,
)
from app.domain.planning_inputs import PlanningResourceCapability
from app.domain.planning_runtime import (
    PLANNING_RUNTIME_OUTPUT_CONTRACT_VERSION,
    PlanningRuntimeAssignment,
    PlanningRuntimeOutputFormatter,
    PlanningRuntimeOutputStatus,
    PlanningRuntimeOutputValidator,
    PlanningRuntimeOutputVersion,
    PlanningRuntimeProducer,
    PlanningRuntimeProducerInput,
    PlanningRuntimeProducerService,
    PlanningRuntimeProductionContext,
    PlanningRuntimeScope,
)
from app.domain.runtime_authority import AuthorityResolutionState
from app.domain.runtime_shadow import (
    PlanningComparator,
    RuntimeShadowPublication,
    RuntimeShadowScope,
    RuntimeShadowService,
    RuntimeShadowSnapshot,
    RuntimeShadowSource,
)
from app.main import app
from app.runtime.planning_output import (
    LegacyPlanningOutputAdapter,
    PlanningRuntimeOutputRuntime,
    PlanningRuntimeShadowBridge,
)
from app.schemas.planning_schema import GeneratePlanningRequest
from app.services.planning_generation_service import generate_planning
from test_execution_attempt import _create_attempt, _intent
from test_execution_intent import NOW, _authority, _publication
from tests.planning_helpers import save_normalized_imports, simple_rows


def _source(intent, **changes) -> PlanningRuntimeProducerInput:
    values = {
        "scope": PlanningRuntimeScope(
            organization_id=intent.scope.organization_id,
            operational_unit_id=intent.scope.operational_unit_id,
            planning_date=intent.scope.planning_date,
            timezone=intent.scope.timezone,
        ),
        "publication": _publication(scope=intent.scope),
        "planning_version": 3,
        "output_version": PlanningRuntimeOutputVersion(sequence=3),
        "resources": (
            HumanResource(
                external_identifier="resource-b",
                display_name="Resource B",
            ),
            HumanResource(
                external_identifier="resource-a",
                display_name="Resource A",
            ),
        ),
        "fleet": (
            AssetReference(external_identifier="asset-b"),
            AssetReference(external_identifier="asset-a"),
        ),
        "assignments": (
            PlanningRuntimeAssignment(
                task_identifier="task-b",
                resource_identifier="resource-b",
                asset_identifier="asset-b",
                state="proposed",
            ),
            PlanningRuntimeAssignment(
                task_identifier="task-a",
                resource_identifier="resource-a",
                asset_identifier="asset-a",
                state="proposed",
            ),
        ),
        "capabilities": (
            PlanningResourceCapability(
                resource_identifier="asset-a",
                resource_kind=ResourceKind.ASSET,
                capability="electric",
            ),
        ),
        "availability": (
            ResourceAvailability(
                resource_identifier="asset-a",
                resource_kind=ResourceKind.ASSET,
                available=True,
                observed_state="available",
            ),
            ResourceAvailability(
                resource_identifier="resource-a",
                resource_kind=ResourceKind.HUMAN_RESOURCE,
                available=True,
                observed_state="available",
            ),
        ),
        "input_fingerprint": "d" * 64,
        "configuration_version": "configuration-v3",
        "rules_version": "rules-v2",
        "evaluation_at": NOW,
    }
    values.update(changes)
    return PlanningRuntimeProducerInput(**values)


def _context(*, source=None, authority_state=None):
    intent = _intent()
    attempt = _create_attempt(intent=intent).attempt
    authority = _authority(scope=intent.scope)
    if authority_state is not None:
        authority = _authority(
            scope=intent.scope,
            state=authority_state,
        )
    return PlanningRuntimeProductionContext(
        source=source or _source(intent),
        authority=authority,
        intent=intent,
        attempt=attempt,
    )


def _service() -> PlanningRuntimeProducerService:
    formatter = PlanningRuntimeOutputFormatter()
    return PlanningRuntimeProducerService(
        producer=PlanningRuntimeProducer(formatter),
        validator=PlanningRuntimeOutputValidator(formatter),
        formatter=formatter,
    )


def test_valid_runtime_output_is_complete_sorted_and_versioned():
    result = _service().produce(_context())

    assert result.status is PlanningRuntimeOutputStatus.READY
    assert result.snapshot is not None
    output = result.snapshot.output
    assert output.version.contract_version == (
        PLANNING_RUNTIME_OUTPUT_CONTRACT_VERSION
    )
    assert output.version.sequence == 3
    assert output.planning_version == 3
    assert output.publication_version == 1
    assert [item.external_identifier for item in output.resources] == [
        "resource-a",
        "resource-b",
    ]
    assert [item.external_identifier for item in output.fleet] == [
        "asset-a",
        "asset-b",
    ]
    assert result.metrics.snapshot_size_bytes == (
        result.snapshot.snapshot_size_bytes
    )
    assert result.metrics.parity_percent is None


def test_output_is_deterministic_for_the_same_input():
    context = _context()

    first = _service().produce(context)
    second = _service().produce(context)

    assert first.snapshot == second.snapshot
    assert first.snapshot.output.fingerprint == second.snapshot.output.fingerprint
    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id


def test_fingerprint_is_canonical_and_tampering_is_rejected():
    formatter = PlanningRuntimeOutputFormatter()
    validator = PlanningRuntimeOutputValidator(formatter)
    result = _service().produce(_context())
    output = result.snapshot.output

    assert output.fingerprint == formatter.fingerprint_output(output)
    tampered = output.model_copy(update={"fingerprint": "e" * 64})
    diagnostics = validator.validate_output(tampered)

    assert diagnostics.valid is False
    assert diagnostics.items[0].code == "OUTPUT_FINGERPRINT_MISMATCH"


def test_snapshot_and_nested_output_are_immutable():
    snapshot = _service().produce(_context()).snapshot

    with pytest.raises(ValidationError):
        snapshot.snapshot_size_bytes = 1
    with pytest.raises(ValidationError):
        snapshot.output.planning_version = 9


def test_fail_closed_rejects_invalid_authority_without_partial_output():
    result = _service().produce(
        _context(authority_state=AuthorityResolutionState.NO_WRITE)
    )

    assert result.status is PlanningRuntimeOutputStatus.REJECTED
    assert result.snapshot is None
    assert result.metrics is None
    assert result.diagnostics.valid is False
    assert result.diagnostics.items[0].code == "AUTHORITY_INVALID"


def test_fail_closed_rejects_unknown_assignment_resource():
    intent = _intent()
    source = _source(
        intent,
        assignments=(
            PlanningRuntimeAssignment(
                task_identifier="task-a",
                resource_identifier="unknown-resource",
                asset_identifier="asset-a",
                state="proposed",
            ),
        ),
    )
    attempt = _create_attempt(intent=intent).attempt
    context = PlanningRuntimeProductionContext(
        source=source,
        authority=_authority(scope=intent.scope),
        intent=intent,
        attempt=attempt,
    )

    result = _service().produce(context)

    assert result.status is PlanningRuntimeOutputStatus.REJECTED
    assert result.snapshot is None
    assert "UNKNOWN_ASSIGNMENT_RESOURCE" in {
        item.code for item in result.diagnostics.items
    }


def test_fail_closed_rejects_duplicate_resources():
    intent = _intent()
    duplicate = HumanResource(external_identifier="resource-a")
    source = _source(intent, resources=(duplicate, duplicate))
    attempt = _create_attempt(intent=intent).attempt
    context = PlanningRuntimeProductionContext(
        source=source,
        authority=_authority(scope=intent.scope),
        intent=intent,
        attempt=attempt,
    )

    result = _service().produce(context)

    assert result.status is PlanningRuntimeOutputStatus.REJECTED
    assert "DUPLICATE_RESOURCE" in {
        item.code for item in result.diagnostics.items
    }


def _legacy_shadow(source, output) -> RuntimeShadowSnapshot:
    assignments = tuple(
        "|".join(
            (
                item.task_identifier,
                item.resource_identifier or "",
                item.asset_identifier or "",
                item.state,
            )
        )
        for item in sorted(
            source.assignments,
            key=lambda item: (
                item.task_identifier,
                item.resource_identifier or "",
                item.asset_identifier or "",
                item.state,
            ),
        )
    )
    capabilities = tuple(
        "|".join(
            (
                item.resource_kind.value,
                item.resource_identifier,
                item.capability,
            )
        )
        for item in sorted(
            source.capabilities,
            key=lambda item: (
                item.resource_kind.value,
                item.resource_identifier,
                item.capability,
            ),
        )
    )
    availability = tuple(
        "|".join(
            (
                item.resource_kind.value,
                item.resource_identifier,
                str(item.available).lower(),
                item.observed_state or "",
            )
        )
        for item in sorted(
            source.availability,
            key=lambda item: (
                item.resource_kind.value,
                item.resource_identifier,
                str(item.available),
                item.observed_state or "",
            ),
        )
    )
    return RuntimeShadowSnapshot(
        source=RuntimeShadowSource.LEGACY,
        scope=RuntimeShadowScope(**source.scope.model_dump(mode="json")),
        publication=RuntimeShadowPublication(
            publication_id=source.publication.publication_id,
            publication_version=source.publication.publication_version,
        ),
        planning_version=source.planning_version,
        resources=tuple(
            sorted(item.external_identifier for item in source.resources)
        ),
        fleet=tuple(sorted(item.external_identifier for item in source.fleet)),
        assignments=assignments,
        capabilities=capabilities,
        availability=availability,
        fingerprint=output.fingerprint,
        input_fingerprint=source.input_fingerprint,
        configuration_version=source.configuration_version,
        rules_version=source.rules_version,
        validation_errors=(),
        evaluation_at=source.evaluation_at,
        generated_at=source.evaluation_at,
    )


def test_real_legacy_bundle_is_produced_and_compared_at_full_parity():
    intent = _intent()
    attempt = _create_attempt(intent=intent).attempt
    planning_rows, fleet_rows = simple_rows(routes=2, drivers=3, vehicles=3)
    planning_import_id, fleet_import_id = save_normalized_imports(
        planning_rows,
        fleet_rows,
    )
    bundle = generate_planning(
        GeneratePlanningRequest(
            planning_import_id=planning_import_id,
            fleet_import_id=fleet_import_id,
            operation_date=intent.scope.planning_date.isoformat(),
        ),
        persist=False,
    )
    source = LegacyPlanningOutputAdapter().adapt(
        bundle=bundle,
        publication=_publication(scope=intent.scope),
        organization_id=intent.scope.organization_id,
        operational_unit_id=intent.scope.operational_unit_id,
        timezone=intent.scope.timezone,
        input_fingerprint="d" * 64,
        configuration_version="legacy-configuration-v1",
        evaluated_at=NOW,
    )
    context = PlanningRuntimeProductionContext(
        source=source,
        authority=_authority(scope=intent.scope),
        intent=intent,
        attempt=attempt,
    )
    producer_service = _service()
    expected = producer_service.produce(context).snapshot.output
    formatter = PlanningRuntimeOutputFormatter()
    bridge = PlanningRuntimeShadowBridge(
        producer_service=producer_service,
        shadow_service=RuntimeShadowService(
            comparator=PlanningComparator(clock=lambda: NOW),
            clock=lambda: NOW,
        ),
        formatter=formatter,
    )

    result = bridge.compare(
        context=context,
        legacy=_legacy_shadow(source, expected),
    )

    assert result.producer.status is PlanningRuntimeOutputStatus.READY
    assert result.shadow.report.perfect_match is True
    assert result.shadow.report.parity_percent == 100
    assert result.producer.metrics.parity_percent == 100
    assert result.shadow.metrics.execution_simulated is True
    assert result.shadow.metrics.duplicate_execution == 0


def test_producer_and_comparator_do_not_write_operational_tables():
    context = _context()
    with db_session() as conn:
        before = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in ("plannings", "assignments", "planning_publications")
        }

    produced = _service().produce(context)
    formatter = PlanningRuntimeOutputFormatter()
    bridge = PlanningRuntimeShadowBridge(
        producer_service=_service(),
        shadow_service=RuntimeShadowService(
            comparator=PlanningComparator(clock=lambda: NOW),
            clock=lambda: NOW,
        ),
        formatter=formatter,
    )
    bridge.compare(
        context=context,
        legacy=_legacy_shadow(context.source, produced.snapshot.output),
    )

    with db_session() as conn:
        after = {
            table: conn.execute(
                f"SELECT COUNT(*) AS total FROM {table}"
            ).fetchone()["total"]
            for table in ("plannings", "assignments", "planning_publications")
        }
    assert after == before


class FixedProductionProvider:
    def __init__(self, context):
        self.context = context

    def get(self, *, scope, publication_id, publication_version):
        return self.context


def _runtime(context) -> PlanningRuntimeOutputRuntime:
    return PlanningRuntimeOutputRuntime(
        service=_service(),
        provider=FixedProductionProvider(context),
        clock=lambda: NOW,
    )


def _endpoint_params():
    return {
        "organization_id": "organization-a",
        "operational_unit_id": "unit-a",
        "planning_date": NOW.date().isoformat(),
        "timezone": "Europe/Rome",
        "publication_id": "publication-a",
        "publication_version": 1,
    }


def test_read_only_endpoint_returns_runtime_snapshot_under_payload_target():
    context = _context()
    app.dependency_overrides[get_planning_runtime_output] = lambda: _runtime(
        context
    )
    try:
        response = TestClient(app).get(
            "/api/runtime/output",
            params=_endpoint_params(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "READY"
    assert response.json()["snapshot"]["output"]["fingerprint"]
    assert len(response.content) < 5 * 1024


def test_endpoint_fails_closed_when_published_payload_is_not_resolvable():
    response = TestClient(app).get(
        "/api/runtime/output",
        params=_endpoint_params(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "NOT_AVAILABLE"
    assert response.json()["snapshot"] is None
    assert response.json()["diagnostics"]["items"][0]["code"] == (
        "RUNTIME_SOURCE_NOT_AVAILABLE"
    )


def test_runtime_rejects_provider_output_from_another_request_scope():
    context = _context()
    runtime = _runtime(context)
    requested_scope = context.source.scope.model_copy(
        update={"operational_unit_id": "unit-b"}
    )

    result = runtime.current(
        scope=requested_scope,
        publication_id=context.source.publication.publication_id,
        publication_version=context.source.publication.publication_version,
    )

    assert result.status is PlanningRuntimeOutputStatus.REJECTED
    assert result.snapshot is None
    assert result.diagnostics.items[0].code == (
        "RUNTIME_REQUEST_SCOPE_MISMATCH"
    )


def test_endpoint_rejects_invalid_timezone_without_stack_trace():
    params = _endpoint_params()
    params["timezone"] = "invalid/timezone"

    response = TestClient(app).get("/api/runtime/output", params=params)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "INVALID_PLANNING_RUNTIME_SCOPE"
    )
    assert "traceback" not in response.text.lower()


def test_openapi_exposes_exactly_one_read_only_runtime_output_operation():
    operation = app.openapi()["paths"]["/api/runtime/output"]

    assert set(operation) == {"get"}


def test_producer_meets_warm_latency_target():
    context = _context()
    service = _service()
    samples = []

    for _ in range(200):
        started = perf_counter()
        result = service.produce(context)
        samples.append(perf_counter() - started)
        assert result.status is PlanningRuntimeOutputStatus.READY

    assert median(samples) < 0.050
