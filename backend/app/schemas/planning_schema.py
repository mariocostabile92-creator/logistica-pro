from pydantic import BaseModel, Field

from app.domain.planning_models import PlanningBundle, PlanningConfiguration


class GeneratePlanningRequest(BaseModel):
    planning_import_id: int | None = None
    fleet_import_id: int | None = None
    operation_date: str | None = None
    station: str | None = None
    configuration: PlanningConfiguration | None = None


class RecalculatePlanningRequest(BaseModel):
    configuration: PlanningConfiguration | None = None
    actor: str = "local_operator"


class PlanningResponse(PlanningBundle):
    pass


class PlanningHistoryResponse(BaseModel):
    planning_id: int
    versions: list[dict[str, object]] = Field(default_factory=list)
    events: list[dict[str, object]] = Field(default_factory=list)
