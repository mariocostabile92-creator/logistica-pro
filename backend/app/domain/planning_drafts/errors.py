class PlanningDraftError(ValueError):
    code = "PLANNING_DRAFT_ERROR"


class PlanningDraftNotFoundError(PlanningDraftError):
    code = "PLANNING_DRAFT_NOT_FOUND"


class PlanningDraftAlreadyExistsError(PlanningDraftError):
    code = "PLANNING_DRAFT_ALREADY_EXISTS"


class PlanningDraftVersionConflictError(PlanningDraftError):
    code = "PLANNING_DRAFT_VERSION_CONFLICT"


class PlanningDraftInvalidStateError(PlanningDraftError):
    code = "PLANNING_DRAFT_INVALID_STATE"


class PlanningDraftSnapshotNotFoundError(PlanningDraftError):
    code = "PLANNING_DRAFT_SNAPSHOT_NOT_FOUND"
