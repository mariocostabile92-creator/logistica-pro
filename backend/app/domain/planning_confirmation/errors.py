class PlanningConfirmationError(Exception):
    code = "PLANNING_CONFIRMATION_ERROR"


class PlanningConfirmationAlreadyExistsError(PlanningConfirmationError):
    code = "PLANNING_CONFIRMATION_ALREADY_EXISTS"
