from pydantic import BaseModel, ConfigDict

from app.domain.runtime_canary import (
    RuntimeCanaryReport,
    RuntimeCanarySession,
    RuntimeCanaryStatus,
)


class RuntimeCanaryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    session: RuntimeCanarySession
    report: RuntimeCanaryReport
    status_history: tuple[RuntimeCanaryStatus, ...]
