import csv
import io

from pydantic import BaseModel, Field, model_validator

from app.utils.text_normalizer import normalize_plate


DEMO_DATASET_VERSION = "demo_dataset_v1"
DEMO_WORKSPACE_ID = "private-beta-demo-v1"
DEMO_ORGANIZATION = "Demo Logistics Italia"
DEMO_OPERATIONAL_UNIT = "HUB-NORD-01"
DEMO_OPERATION_DATE = "2099-01-15"
DEMO_CREATED_BY = "demo_workspace_loader"


class DemoHumanResource(BaseModel):
    external_identifier: str
    display_name: str


class DemoAssetSeed(BaseModel):
    external_identifier: str
    plate: str
    driver_id: str | None = None
    driver_name: str | None = None
    second_driver_id: str | None = None
    second_driver_name: str | None = None
    availability: str = "available"
    status: str = "active"
    import_status: str = "Operativo"
    capabilities: list[str] = Field(default_factory=list)


class DemoTaskSeed(BaseModel):
    external_identifier: str
    driver_id: str
    driver_name: str
    vehicle_plate: str
    time_window: str
    required_capabilities: list[str] = Field(default_factory=list)


class DemoDataset(BaseModel):
    version: str
    workspace_id: str
    organization: str
    operational_unit: str
    operation_date: str
    human_resources: list[DemoHumanResource]
    assets: list[DemoAssetSeed]
    tasks: list[DemoTaskSeed]
    absent_human_resource_id: str

    @model_validator(mode="after")
    def validate_demo_shape(self):
        if len(self.tasks) < 10:
            raise ValueError("Il dataset demo richiede almeno 10 Task.")
        if len(self.human_resources) < 12:
            raise ValueError(
                "Il dataset demo richiede almeno 12 Human Resource."
            )
        if len(self.assets) < 11:
            raise ValueError("Il dataset demo richiede almeno 11 Asset.")
        if len({item.time_window for item in self.tasks}) < 2:
            raise ValueError("Il dataset demo richiede due Time Window.")
        if sum(item.availability == "unavailable" for item in self.assets) != 1:
            raise ValueError("Il dataset demo richiede un Asset indisponibile.")
        if sum(item.availability == "reserve" for item in self.assets) != 1:
            raise ValueError("Il dataset demo richiede un Asset in riserva.")
        if not any(item.required_capabilities for item in self.tasks):
            raise ValueError(
                "Il dataset demo richiede almeno una capability."
            )
        resource_ids = {
            item.external_identifier for item in self.human_resources
        }
        if self.absent_human_resource_id not in resource_ids:
            raise ValueError("La Human Resource assente non esiste.")
        if len(resource_ids) != len(self.human_resources):
            raise ValueError("Gli ID Human Resource devono essere univoci.")
        if len({item.external_identifier for item in self.assets}) != len(
            self.assets
        ):
            raise ValueError("Gli ID Asset devono essere univoci.")
        if len({item.external_identifier for item in self.tasks}) != len(
            self.tasks
        ):
            raise ValueError("Gli ID Task devono essere univoci.")
        return self


def build_demo_dataset() -> DemoDataset:
    resources = [
        DemoHumanResource(
            external_identifier=f"DRV-DEMO-{index:03d}",
            display_name=f"Demo Driver {index:02d}",
        )
        for index in range(1, 13)
    ]
    assets: list[DemoAssetSeed] = []
    for index in range(1, 12):
        driver_id = f"DRV-DEMO-{index:03d}" if index <= 9 else None
        driver_name = f"Demo Driver {index:02d}" if index <= 9 else None
        second_driver_id = None
        second_driver_name = None
        if index == 1:
            second_driver_id = "DRV-DEMO-011"
            second_driver_name = "Demo Driver 11"
        elif index == 2:
            second_driver_id = "DRV-DEMO-012"
            second_driver_name = "Demo Driver 12"
        elif index == 11:
            second_driver_id = "DRV-DEMO-010"
            second_driver_name = "Demo Driver 10"

        availability = "available"
        status = "active"
        import_status = "Operativo"
        if index == 10:
            availability = "reserve"
            import_status = "Riserva"
        elif index == 11:
            availability = "unavailable"
            status = "maintenance"
            import_status = "Manutenzione"

        capabilities: list[str] = []
        if index == 1:
            capabilities = ["large_capacity"]
        elif index == 2:
            capabilities = ["electric"]
        elif index == 3:
            capabilities = ["refrigerated"]

        assets.append(
            DemoAssetSeed(
                external_identifier=f"AST-DEMO-{index:03d}",
                plate=f"DEMO-{index:03d}",
                driver_id=driver_id,
                driver_name=driver_name,
                second_driver_id=second_driver_id,
                second_driver_name=second_driver_name,
                availability=availability,
                status=status,
                import_status=import_status,
                capabilities=capabilities,
            )
        )

    tasks = [
        DemoTaskSeed(
            external_identifier=f"TASK-DEMO-{index:03d}",
            driver_id=f"DRV-DEMO-{index:03d}",
            driver_name=f"Demo Driver {index:02d}",
            vehicle_plate=f"DEMO-{index:03d}",
            time_window=(
                "WAVE-DEMO-A"
                if index <= 5
                else "WAVE-DEMO-B"
            ),
            required_capabilities=(
                ["large_capacity"] if index == 1 else []
            ),
        )
        for index in range(1, 11)
    ]
    return DemoDataset(
        version=DEMO_DATASET_VERSION,
        workspace_id=DEMO_WORKSPACE_ID,
        organization=DEMO_ORGANIZATION,
        operational_unit=DEMO_OPERATIONAL_UNIT,
        operation_date=DEMO_OPERATION_DATE,
        human_resources=resources,
        assets=assets,
        tasks=tasks,
        absent_human_resource_id="DRV-DEMO-001",
    )


def _csv_bytes(
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def planning_csv_bytes(dataset: DemoDataset) -> bytes:
    fields = [
        "Human Resource ID",
        "Driver",
        "Vehicle",
        "Station",
        "Route",
        "Wave",
        "Required Capability",
    ]
    rows = [
        {
            "Human Resource ID": task.driver_id,
            "Driver": task.driver_name,
            "Vehicle": task.vehicle_plate,
            "Station": dataset.operational_unit,
            "Route": task.external_identifier,
            "Wave": task.time_window,
            "Required Capability": ", ".join(task.required_capabilities),
        }
        for task in dataset.tasks
    ]
    return _csv_bytes(fields, rows)


def fleet_csv_bytes(dataset: DemoDataset) -> bytes:
    fields = [
        "Asset ID",
        "Targa",
        "Driver ID",
        "Driver",
        "Second Driver ID",
        "Second Driver",
        "Status",
        "Station",
        "Modello",
        "Note",
    ]
    rows = [
        {
            "Asset ID": asset.external_identifier,
            "Targa": asset.plate,
            "Driver ID": asset.driver_id or "",
            "Driver": asset.driver_name or "",
            "Second Driver ID": asset.second_driver_id or "",
            "Second Driver": asset.second_driver_name or "",
            "Status": asset.import_status,
            "Station": dataset.operational_unit,
            "Modello": "Demo Van",
            "Note": (
                "Asset sintetico in riserva"
                if asset.availability == "reserve"
                else "Asset sintetico Private Beta"
            ),
        }
        for asset in dataset.assets
    ]
    return _csv_bytes(fields, rows)


def demo_import_filenames(dataset: DemoDataset) -> tuple[str, str]:
    prefix = f"DEMO__{dataset.workspace_id}__{dataset.version}"
    return f"{prefix}__planning.csv", f"{prefix}__fleet.csv"


def demo_import_signatures(
    dataset: DemoDataset,
) -> dict[str, tuple[str, str, frozenset[str]]]:
    planning_filename, fleet_filename = demo_import_filenames(dataset)
    return {
        planning_filename: (
            "planning",
            "route",
            frozenset(item.external_identifier for item in dataset.tasks),
        ),
        fleet_filename: (
            "fleet",
            "vehicle_plate",
            frozenset(normalize_plate(item.plate) for item in dataset.assets),
        ),
    }
