from collections.abc import Iterable


class PlanningComparatorFormatter:
    @staticmethod
    def value(value: object) -> str:
        if isinstance(value, tuple):
            rendered = "[" + ", ".join(sorted(str(item) for item in value)) + "]"
        else:
            rendered = str(value)
        return rendered[:1_000]

    @staticmethod
    def difference(
        *,
        missing: Iterable[str] = (),
        unexpected: Iterable[str] = (),
        legacy_value: object | None = None,
        runtime_value: object | None = None,
    ) -> str:
        missing_values = tuple(sorted(str(item) for item in missing))
        unexpected_values = tuple(sorted(str(item) for item in unexpected))
        if missing_values or unexpected_values:
            rendered = (
                f"missing={list(missing_values)}; "
                f"unexpected={list(unexpected_values)}"
            )
        else:
            rendered = (
                f"legacy={legacy_value}; runtime={runtime_value}"
            )
        return rendered[:1_000]
