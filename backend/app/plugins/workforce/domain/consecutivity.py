from pydantic import BaseModel, Field, model_validator


class ConsecutivityPolicy(BaseModel):
    organization_id: str
    warning_threshold: int = Field(default=5, ge=1, le=30)
    rest_required_threshold: int = Field(default=6, ge=2, le=31)
    rest_break_days: int = Field(default=1, ge=1, le=7)
    updated_by: str = "platform"
    updated_at: str

    @model_validator(mode="after")
    def validate_thresholds(self):
        if self.warning_threshold >= self.rest_required_threshold:
            raise ValueError("La soglia di attenzione deve precedere la soglia limite.")
        return self


class ConsecutivityOverride(BaseModel):
    id: str
    organization_id: str
    workforce_member_id: int
    operation_date: str
    valid_until: str
    target_callability: str
    reason: str = Field(min_length=1)
    created_by: str
    created_at: str
    revoked_at: str | None = None


class ConsecutivityDay(BaseModel):
    date: str
    state: str
    source: str
    worked: bool = False
    planned: bool = False
    reason: str


class ConsecutivitySnapshot(BaseModel):
    driver_id: int
    operation_date: str
    organization_id: str
    effective_consecutive_days: int | None = None
    planned_consecutive_days: int | None = None
    last_worked_date: str | None = None
    last_rest_date: str | None = None
    next_planned_work_date: str | None = None
    threshold_warning: int
    threshold_rest_required: int
    status: str
    calculated_status: str
    reason: str = Field(min_length=1)
    source_summary: list[str] = Field(default_factory=list)
    calculated_at: str
    analyzed_from: str
    analyzed_to: str
    sequence: list[ConsecutivityDay] = Field(default_factory=list)
    override: ConsecutivityOverride | None = None
    expired_override: ConsecutivityOverride | None = None
    policy_message: str = "Valutazione basata sulla policy operativa dell'organizzazione."
