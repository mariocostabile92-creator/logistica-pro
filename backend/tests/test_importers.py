from app.adapters.amazon import AMAZON_ADAPTER
from app.importers.fleet_importer import normalize_fleet_rows
from app.importers.planning_importer import normalize_planning_rows
from app.services.normalization_service import suggest_mapping


def test_small_planning_import():
    rows = [{"Driver": "Mario Rossi", "Targa": "AB123CD", "Route": "R1"}]
    mapping = suggest_mapping(
        list(rows[0]),
        AMAZON_ADAPTER.aliases_for("planning"),
    )
    normalized = normalize_planning_rows(rows, mapping)
    assert normalized[0].driver_key == "mariorossi"
    assert normalized[0].vehicle_plate == "AB123CD"
    assert normalized[0].route == "R1"


def test_small_fleet_import():
    rows = [{"Targa": "AB123CD", "Autista": "Mario Rossi", "Stato": "Operativo", "Officina": ""}]
    mapping = suggest_mapping(
        list(rows[0]),
        AMAZON_ADAPTER.aliases_for("fleet"),
    )
    normalized = normalize_fleet_rows(rows, mapping)
    assert normalized[0].driver_key == "mariorossi"
    assert normalized[0].vehicle_plate == "AB123CD"
    assert normalized[0].status == "Operativo"
