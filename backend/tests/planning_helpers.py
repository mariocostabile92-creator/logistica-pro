import csv
from pathlib import Path

from app.adapters.amazon import AMAZON_ADAPTER
from app.domain.normalized_models import NormalizedFleetRow, NormalizedPlanningRow
from app.importers.fleet_importer import normalize_fleet_rows
from app.importers.planning_importer import normalize_planning_rows
from app.repositories.import_repository import save_import
from app.services.normalization_service import suggest_mapping


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_csv_fixture(name: str) -> list[dict[str, object]]:
    with (FIXTURE_DIR / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def realistic_normalized_rows():
    planning_raw = load_csv_fixture("realistic_planning.csv")
    fleet_raw = load_csv_fixture("realistic_fleet.csv")
    planning = normalize_planning_rows(
        planning_raw,
        suggest_mapping(
            list(planning_raw[0]),
            AMAZON_ADAPTER.aliases_for("planning"),
        ),
    )
    fleet = normalize_fleet_rows(
        fleet_raw,
        suggest_mapping(
            list(fleet_raw[0]),
            AMAZON_ADAPTER.aliases_for("fleet"),
        ),
    )
    return planning, fleet


def save_normalized_imports(
    planning_rows: list[NormalizedPlanningRow],
    fleet_rows: list[NormalizedFleetRow],
) -> tuple[int, int]:
    planning_id = save_import(
        "planning",
        "synthetic-planning.csv",
        None,
        [],
        [row.model_dump(mode="json") for row in planning_rows],
    )
    fleet_id = save_import(
        "fleet",
        "synthetic-fleet.csv",
        None,
        [],
        [row.model_dump(mode="json") for row in fleet_rows],
    )
    return planning_id, fleet_id


def save_realistic_imports() -> tuple[int, int]:
    return save_normalized_imports(*realistic_normalized_rows())


def simple_rows(
    routes: int = 2,
    drivers: int = 3,
    vehicles: int = 3,
    station: str = "DLO1",
) -> tuple[list[NormalizedPlanningRow], list[NormalizedFleetRow]]:
    planning = [
        NormalizedPlanningRow(
            row_number=index + 2,
            station=station,
            route=f"R{index + 1:03d}",
            cycle="W1",
            driver_name=f"Driver {index + 1:02d}" if index < drivers else None,
            driver_key=f"driver{index + 1:02d}" if index < drivers else None,
        )
        for index in range(routes)
    ]
    fleet = [
        NormalizedFleetRow(
            row_number=index + 2,
            station=station,
            vehicle_plate=f"AA{index + 1:03d}AA",
            driver_name=f"Driver {index + 1:02d}" if index < drivers else None,
            driver_key=f"driver{index + 1:02d}" if index < drivers else None,
            status="Operativo",
        )
        for index in range(vehicles)
    ]
    return planning, fleet
