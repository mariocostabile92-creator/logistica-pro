COMPLETED_STATUSES = {"completed", "con_anomalia"}


def apply_filter(items: list[dict], completion: dict, selected: str | None) -> tuple[list[dict], dict]:
    if not selected or selected in {"all", "drivers_expected"}:
        return items, completion
    missing = completion["missing"]
    if selected.startswith("checkout_"):
        operation = "check_out"
    elif selected.startswith("checkin_"):
        operation = "check_in"
    else:
        operation = None
    if operation:
        items = [item for item in items if item["operation_type"] == operation]
        missing = [item for item in missing if item["operation_type"] == operation]
        if selected.endswith("_completed"):
            items = [item for item in items if item["status"] in COMPLETED_STATUSES]
            missing = []
        elif selected.endswith("_missing"):
            items = []
    elif selected == "procedures_open":
        items = [item for item in items if item["status"] in {"generated", "opened"}]
        missing = []
    elif selected == "procedures_in_progress":
        items = [item for item in items if item["status"] == "in_progress"]
        missing = []
    elif selected == "procedures_late":
        items = [item for item in items if item.get("is_late")]
        missing = [item for item in missing if item["status"] in {"in_ritardo", "critico"}]
    elif selected == "procedures_anomaly":
        items = [item for item in items if item.get("anomaly_present")]
        missing = []
    return items, {**completion, "missing": missing, "active_filter": selected}
