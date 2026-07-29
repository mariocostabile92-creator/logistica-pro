from app.domain.core_language.models import Task


class RouteMapper:
    @staticmethod
    def to_core(route: str | None) -> Task | None:
        if route is None or route == "":
            return None
        return Task(external_identifier=route)

    @staticmethod
    def to_legacy(task: Task | None) -> str | None:
        return task.external_identifier if task else None
