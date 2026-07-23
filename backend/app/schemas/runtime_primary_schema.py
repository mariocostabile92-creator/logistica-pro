from pydantic import BaseModel, ConfigDict

from app.domain.runtime_primary import RuntimePrimaryReport


class RuntimePrimaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    report: RuntimePrimaryReport
