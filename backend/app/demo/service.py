import logging
from threading import Lock
from typing import Any

from app.adapters.registry import get_active_tabular_import_adapter
from app.demo import repository
from app.demo.dataset_factory import (
    DEMO_CREATED_BY,
    DEMO_DATASET_VERSION,
    DEMO_WORKSPACE_ID,
    DemoDataset,
    build_demo_dataset,
    demo_import_filenames,
    demo_import_signatures,
    fleet_csv_bytes,
    planning_csv_bytes,
)
from app.demo.schemas import (
    DemoDatasetCounts,
    DemoLoadResponse,
    DemoRemovedCounts,
    DemoResetResponse,
    DemoStatusResponse,
    DemoWorkspaceState,
    DemoWorkspaceSummary,
)
from app.domain.operation_events import (
    OperationEntityType,
    OperationEventType,
)
from app.plugins.fleet.application.asset_service import (
    add_document,
    create_asset,
    list_events as list_asset_events,
)
from app.plugins.fleet.interfaces.schemas import (
    AssetCreateRequest,
    AssetDocumentCreateRequest,
)
from app.schemas.planning_event_schema import PlanningEventRequest
from app.schemas.planning_schema import GeneratePlanningRequest
from app.services.exception_simulation_service import apply_event
from app.services.import_service import import_tabular_content
from app.services.operations_engine import evaluate_latest_operations
from app.services.planning_generation_service import generate_planning
from app.utils.date_utils import utc_now_iso


logger = logging.getLogger("operations_engine.demo")
_LOAD_LOCK = Lock()


class DemoWorkspaceLoadError(RuntimeError):
    pass


class DemoWorkspaceResetError(RuntimeError):
    pass


def _base_metadata(dataset: DemoDataset) -> dict[str, Any]:
    return {
        "organization": dataset.organization,
        "operational_unit": dataset.operational_unit,
        "operation_date": dataset.operation_date,
        "import_ids": [],
        "asset_ids": [],
        "planning_ids": [],
        "operation_snapshot_ids": [],
        "audit": [],
        "summary": None,
    }


def _append_audit(
    metadata: dict[str, Any],
    action: str,
    state: DemoWorkspaceState,
    occurred_at: str,
) -> None:
    audit = metadata.setdefault("audit", [])
    audit.append(
        {
            "action": action,
            "state": state.value,
            "occurred_at": occurred_at,
            "actor": DEMO_CREATED_BY,
        }
    )


def _save_state(
    dataset: DemoDataset,
    metadata: dict[str, Any],
    state: DemoWorkspaceState,
    *,
    created_at: str,
    reset_at: str | None = None,
) -> None:
    updated_at = utc_now_iso()
    _append_audit(metadata, "state_changed", state, updated_at)
    repository.save_workspace(
        demo_workspace_id=dataset.workspace_id,
        dataset_version=dataset.version,
        status=state.value,
        created_at=created_at,
        created_by=DEMO_CREATED_BY,
        updated_at=updated_at,
        reset_at=reset_at,
        metadata=metadata,
    )


def _summary_from_record(
    record: dict[str, Any],
) -> DemoWorkspaceSummary | None:
    summary = record["metadata"].get("summary")
    if not summary:
        return None
    return DemoWorkspaceSummary.model_validate(summary)


def get_demo_status() -> DemoStatusResponse:
    record = repository.get_workspace(DEMO_WORKSPACE_ID)
    if not record:
        return DemoStatusResponse(
            present=False,
            status=DemoWorkspaceState.NO_DEMO,
        )
    state = DemoWorkspaceState(record["status"])
    return DemoStatusResponse(
        present=state not in {
            DemoWorkspaceState.NO_DEMO,
            DemoWorkspaceState.RESET,
        },
        status=state,
        summary=_summary_from_record(record),
    )


def _asset_values(asset) -> dict[str, object]:
    request = AssetCreateRequest(
        external_identifier=asset.external_identifier,
        plate=asset.plate,
        category="light_van",
        status=asset.status,
        availability=asset.availability,
        notes=(
            f"DEMO {DEMO_DATASET_VERSION}. "
            "Dato sintetico, non usare per operazioni reali."
        ),
        capabilities=asset.capabilities,
        actor=DEMO_CREATED_BY,
    )
    return request.model_dump(exclude={"actor"})


def _add_demo_documents(asset_ids: list[int]) -> None:
    documents = (
        {
            "document_type": "insurance",
            "name": "Demo Insurance 2099",
            "reference": "DEMO-DOC-INS-001",
            "issued_on": "2099-01-01",
            "expires_on": "2099-12-31",
            "notes": "Documento sintetico del Demo Workspace.",
        },
        {
            "document_type": "inspection",
            "name": "Demo Inspection 2099",
            "reference": "DEMO-DOC-REV-002",
            "issued_on": "2099-01-02",
            "expires_on": "2099-07-02",
            "notes": "Documento sintetico del Demo Workspace.",
        },
    )
    for asset_id, document in zip(asset_ids, documents):
        request = AssetDocumentCreateRequest(
            **document,
            actor=DEMO_CREATED_BY,
        )
        add_document(
            asset_id,
            request.model_dump(exclude={"actor"}),
            actor=DEMO_CREATED_BY,
        )


def _workspace_summary(
    dataset: DemoDataset,
    *,
    created_at: str,
    planning_bundle,
    dashboard,
    asset_ids: list[int],
) -> DemoWorkspaceSummary:
    assignment_warning_codes = {
        warning
        for assignment in planning_bundle.assignments
        for warning in assignment.warnings
    }
    dashboard_warning_codes = {
        issue.code
        for issue in dashboard.issues
        if issue.severity.value != "critical"
    }
    warning_codes = sorted(
        assignment_warning_codes | dashboard_warning_codes
    )
    alternatives = sum(
        len(assignment.alternatives)
        for assignment in planning_bundle.assignments
    )
    asset_events = sum(
        len(list_asset_events(asset_id))
        for asset_id in asset_ids
    )
    planning_events = len(planning_bundle.history.get("events", []))
    return DemoWorkspaceSummary(
        demo_workspace_id=dataset.workspace_id,
        dataset_version=dataset.version,
        status=DemoWorkspaceState.READY,
        organization=dataset.organization,
        operational_unit=dataset.operational_unit,
        operation_date=dataset.operation_date,
        created_at=created_at,
        created_by=DEMO_CREATED_BY,
        planning_id=planning_bundle.planning.id,
        planning_status=planning_bundle.planning.status.value,
        readiness_status=dashboard.readiness.status.value,
        warning_codes=warning_codes,
        counts=DemoDatasetCounts(
            tasks=len(dataset.tasks),
            human_resources=len(dataset.human_resources),
            absent_human_resources=1,
            assets=len(dataset.assets),
            unavailable_assets=sum(
                item.availability == "unavailable"
                for item in dataset.assets
            ),
            reserve_assets=sum(
                item.availability == "reserve"
                for item in dataset.assets
            ),
            time_windows=len(
                {item.time_window for item in dataset.tasks}
            ),
            warnings=len(warning_codes),
            alternatives=alternatives,
            events=asset_events + planning_events,
        ),
    )


def _cleanup(
    dataset: DemoDataset,
    metadata: dict[str, Any],
) -> dict[str, int]:
    return repository.remove_demo_entities(
        metadata,
        import_signatures=demo_import_signatures(dataset),
        asset_external_identifiers=[
            item.external_identifier for item in dataset.assets
        ],
        actor=DEMO_CREATED_BY,
    )


def load_demo_workspace() -> DemoLoadResponse:
    dataset = build_demo_dataset()
    with _LOAD_LOCK:
        current = repository.get_workspace(dataset.workspace_id)
        if (
            current
            and current["status"] == DemoWorkspaceState.READY.value
            and repository.demo_entities_complete(current["metadata"])
        ):
            summary = _summary_from_record(current)
            if summary:
                return DemoLoadResponse(
                    created=False,
                    idempotent=True,
                    summary=summary,
                )

        if current:
            _cleanup(dataset, current["metadata"])

        created_at = utc_now_iso()
        metadata = _base_metadata(dataset)
        _save_state(
            dataset,
            metadata,
            DemoWorkspaceState.LOADING,
            created_at=created_at,
        )

        try:
            planning_filename, fleet_filename = demo_import_filenames(
                dataset
            )
            adapter = get_active_tabular_import_adapter()
            planning_import = import_tabular_content(
                content=planning_csv_bytes(dataset),
                original_filename=planning_filename,
                dataset_type="planning",
                adapter=adapter,
            )
            metadata["import_ids"].append(planning_import.import_id)
            _save_state(
                dataset,
                metadata,
                DemoWorkspaceState.PARTIAL,
                created_at=created_at,
            )

            fleet_import = import_tabular_content(
                content=fleet_csv_bytes(dataset),
                original_filename=fleet_filename,
                dataset_type="fleet",
                adapter=adapter,
            )
            metadata["import_ids"].append(fleet_import.import_id)
            _save_state(
                dataset,
                metadata,
                DemoWorkspaceState.PARTIAL,
                created_at=created_at,
            )

            for asset_seed in dataset.assets:
                asset = create_asset(
                    _asset_values(asset_seed),
                    actor=DEMO_CREATED_BY,
                )
                metadata["asset_ids"].append(int(asset.id))
                _save_state(
                    dataset,
                    metadata,
                    DemoWorkspaceState.PARTIAL,
                    created_at=created_at,
                )
            _add_demo_documents(metadata["asset_ids"])

            planning_bundle = generate_planning(
                GeneratePlanningRequest(
                    planning_import_id=planning_import.import_id,
                    fleet_import_id=fleet_import.import_id,
                    operation_date=dataset.operation_date,
                ),
                actor=DEMO_CREATED_BY,
            )
            planning_id = int(planning_bundle.planning.id)
            metadata["planning_ids"].append(planning_id)
            _save_state(
                dataset,
                metadata,
                DemoWorkspaceState.PARTIAL,
                created_at=created_at,
            )

            planning_bundle, _, _ = apply_event(
                planning_id,
                PlanningEventRequest(
                    event_type=OperationEventType.DRIVER_ABSENT,
                    entity_type=OperationEntityType.DRIVER,
                    entity_id="Demo Driver 01",
                    reason=(
                        "Assenza sintetica prevista dal Demo Workspace."
                    ),
                    actor=DEMO_CREATED_BY,
                ),
            )
            dashboard = evaluate_latest_operations(
                reserve_threshold=1,
                recognized_operational_units=(
                    adapter.recognized_operational_units()
                ),
            )
            if dashboard.analysis_id is not None:
                metadata["operation_snapshot_ids"].append(
                    dashboard.analysis_id
                )

            summary = _workspace_summary(
                dataset,
                created_at=created_at,
                planning_bundle=planning_bundle,
                dashboard=dashboard,
                asset_ids=metadata["asset_ids"],
            )
            metadata["summary"] = summary.model_dump(mode="json")
            _save_state(
                dataset,
                metadata,
                DemoWorkspaceState.READY,
                created_at=created_at,
            )
            return DemoLoadResponse(
                created=True,
                idempotent=False,
                summary=summary,
            )
        except Exception as exc:
            logger.exception(
                "Demo workspace load failed workspace_id=%s",
                dataset.workspace_id,
            )
            try:
                metadata["cleanup_after_failure"] = _cleanup(
                    dataset,
                    metadata,
                )
            except Exception:
                logger.exception(
                    "Demo workspace cleanup failed workspace_id=%s",
                    dataset.workspace_id,
                )
            metadata["error_code"] = "DEMO_LOAD_FAILED"
            _save_state(
                dataset,
                metadata,
                DemoWorkspaceState.FAILED,
                created_at=created_at,
            )
            raise DemoWorkspaceLoadError(
                "Il workspace demo non e stato caricato. "
                "Nessun dato reale e stato modificato."
            ) from exc


def reset_demo_workspace() -> DemoResetResponse:
    dataset = build_demo_dataset()
    with _LOAD_LOCK:
        current = repository.get_workspace(dataset.workspace_id)
        created_at = (
            current["created_at"] if current else utc_now_iso()
        )
        metadata = (
            current["metadata"] if current else _base_metadata(dataset)
        )
        try:
            removed = _cleanup(dataset, metadata)
        except Exception as exc:
            logger.exception(
                "Demo workspace reset failed workspace_id=%s",
                dataset.workspace_id,
            )
            raise DemoWorkspaceResetError(
                "Il reset demo non e stato completato. "
                "I dati reali non sono stati modificati."
            ) from exc

        idempotent = not any(removed.values())
        reset_at = utc_now_iso()
        metadata["import_ids"] = []
        metadata["asset_ids"] = []
        metadata["planning_ids"] = []
        metadata["operation_snapshot_ids"] = []
        metadata["summary"] = None
        metadata["last_reset"] = {
            "occurred_at": reset_at,
            "removed": removed,
        }
        _save_state(
            dataset,
            metadata,
            DemoWorkspaceState.RESET,
            created_at=created_at,
            reset_at=reset_at,
        )
        return DemoResetResponse(
            demo_workspace_id=dataset.workspace_id,
            idempotent=idempotent,
            removed=DemoRemovedCounts.model_validate(removed),
        )
