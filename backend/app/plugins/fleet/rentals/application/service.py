from app.plugins.fleet.rentals.infrastructure import repository


class RentalError(ValueError):
    status_code = 422


class RentalNotFound(RentalError):
    status_code = 404


def list_rentals(vehicle_id=None):
    items = repository.list_all(vehicle_id)
    return {
        "items": items,
        "summary": {
            "active": sum(item["status"] in {"attivo", "prorogato"} for item in items),
            "scheduled": sum(item["status"] == "programmato" for item in items),
            "completed": sum(item["status"] == "concluso" for item in items),
            "replaced_vehicles": len({
                item["vehicle_id"] for item in items
                if item["vehicle_id"] and item["status"] in {"attivo", "prorogato"}
            }),
        },
    }


def get_rental(rental_id):
    item = repository.get(rental_id)
    if not item:
        raise RentalNotFound("Noleggio non trovato.")
    return item


def create_rental(values, actor):
    context = repository.context(
        values.get("vehicle_id"), values.get("damage_case_id"),
        values.get("maintenance_id"),
    )
    if context is None:
        raise RentalNotFound("Origine operativa non trovata.")
    if not values.get("vehicle_id"):
        values["vehicle_id"] = context.get("vehicle_id")
    return repository.create(values)


def update_rental(rental_id, changes, actor):
    current = get_rental(rental_id)
    start = changes.get("start_date", current["start_date"])
    end = changes.get("expected_end_date", current["expected_end_date"])
    if end < start:
        raise RentalError("La fine prevista non può precedere l'inizio.")
    item = repository.update(rental_id, changes)
    if not item:
        raise RentalNotFound("Noleggio non trovato.")
    return item
