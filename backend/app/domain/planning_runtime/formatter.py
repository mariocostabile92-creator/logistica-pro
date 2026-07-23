import hashlib
import json

from app.domain.planning_runtime.models import PlanningRuntimeOutput


class PlanningRuntimeOutputFormatter:
    @staticmethod
    def canonical_json(payload: dict[str, object]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    def fingerprint_payload(self, payload: dict[str, object]) -> str:
        canonical = self.canonical_json(payload)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def fingerprint_output(self, output: PlanningRuntimeOutput) -> str:
        payload = output.model_dump(
            mode="json",
            exclude={"fingerprint"},
        )
        return self.fingerprint_payload(payload)

    @staticmethod
    def snapshot_size(output: PlanningRuntimeOutput) -> int:
        return len(output.model_dump_json().encode("utf-8"))

    @staticmethod
    def resources(output: PlanningRuntimeOutput) -> tuple[str, ...]:
        return tuple(item.external_identifier for item in output.resources)

    @staticmethod
    def fleet(output: PlanningRuntimeOutput) -> tuple[str, ...]:
        return tuple(item.external_identifier for item in output.fleet)

    @staticmethod
    def assignments(output: PlanningRuntimeOutput) -> tuple[str, ...]:
        return tuple(
            "|".join(
                (
                    item.task_identifier,
                    item.resource_identifier or "",
                    item.asset_identifier or "",
                    item.state,
                )
            )
            for item in output.assignments
        )

    @staticmethod
    def capabilities(output: PlanningRuntimeOutput) -> tuple[str, ...]:
        return tuple(
            "|".join(
                (
                    item.resource_kind.value,
                    item.resource_identifier,
                    item.capability,
                )
            )
            for item in output.capabilities
        )

    @staticmethod
    def availability(output: PlanningRuntimeOutput) -> tuple[str, ...]:
        return tuple(
            "|".join(
                (
                    item.resource_kind.value,
                    item.resource_identifier,
                    str(item.available).lower(),
                    item.observed_state or "",
                )
            )
            for item in output.availability
        )
