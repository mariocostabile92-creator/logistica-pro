from app.plugins.fleet.franchises.infrastructure import repository


class FranchiseError(ValueError):
    status_code = 422


class FranchiseNotFound(FranchiseError):
    status_code = 404


def _serialize(item):
    if not item:
        return item
    result = dict(item)
    result["contract_company"] = result.get("company") or result.get("owner_company")
    result["franchise_expected"] = result.get("deductible")
    result["has_contract_franchise"] = result.get("deductible") is not None
    for field in ("company", "owner_company", "deductible"):
        result.pop(field, None)
    return result


def list_cases(vehicle_id: int | None = None):
    items = [_serialize(item) for item in repository.list_all(vehicle_id)]
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "to_evaluate": sum(item["status"] == "da_valutare" for item in items),
            "in_review": sum(item["status"] == "in_verifica" for item in items),
            "applied": sum(item["status"] == "applicata" for item in items),
            "closed": sum(item["status"] == "chiusa" for item in items),
        },
    }


def get_case(case_id: int):
    item = repository.get(case_id)
    if not item:
        raise FranchiseNotFound("Valutazione franchigia non trovata.")
    return _serialize(item)


def ensure_for_damage(values: dict[str, object], actor: str):
    existing = repository.get_by_damage(int(values["damage_case_id"]))
    if existing:
        return _serialize(existing)
    damage = repository.damage_context(int(values["damage_case_id"]))
    if not damage:
        raise FranchiseNotFound("Pratica danno non trovata.")
    return _serialize(repository.create({
        **values,
        "vehicle_id": damage["vehicle_id"],
        "maintenance_id": damage.get("maintenance_id"),
    }))


def update_case(case_id: int, changes: dict[str, object], actor: str):
    item = repository.update(case_id, changes)
    if not item:
        raise FranchiseNotFound("Valutazione franchigia non trovata.")
    return _serialize(item)
