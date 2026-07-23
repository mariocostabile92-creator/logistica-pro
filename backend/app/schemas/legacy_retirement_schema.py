from pydantic import BaseModel, ConfigDict

from app.domain.legacy_retirement import LegacyRetirementReport


class LegacyRetirementResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    report: LegacyRetirementReport
