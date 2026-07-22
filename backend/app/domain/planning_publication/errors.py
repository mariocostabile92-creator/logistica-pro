class PlanningPublicationError(Exception):
    code = "PLANNING_PUBLICATION_ERROR"


class PlanningPublicationAlreadyExistsError(PlanningPublicationError):
    code = "PLANNING_PUBLICATION_ALREADY_EXISTS"
