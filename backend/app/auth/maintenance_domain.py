from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field


class MaintenanceScope(StrEnum):
    PLANNING_COVERAGE_BACKFILL = "PLANNING_COVERAGE_BACKFILL"
    WORKFORCE_OPERATIONAL_CYCLE_BACKFILL = (
        "WORKFORCE_OPERATIONAL_CYCLE_BACKFILL"
    )


class MaintenanceTokenStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class MaintenanceTokenCreateRequest(BaseModel):
    scope: MaintenanceScope
    ttl_minutes: int = Field(default=15, ge=1, le=30)


class MaintenanceTokenCreated(BaseModel):
    id: str
    token: str
    scope: MaintenanceScope
    expires_at: str


@dataclass(frozen=True)
class MaintenancePrincipal:
    token_id: str
    organization_id: str
    scope: MaintenanceScope
    created_by: str
