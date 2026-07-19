import ast
from pathlib import Path


APP_DIR = Path(__file__).parents[1] / "app"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def python_files(*parts: str) -> list[Path]:
    root = APP_DIR.joinpath(*parts)
    return sorted(root.rglob("*.py")) if root.exists() else []


def assert_no_imports(paths: list[Path], forbidden: tuple[str, ...]) -> None:
    violations: list[str] = []
    for path in paths:
        for module in imported_modules(path):
            if module.startswith(forbidden):
                relative = path.relative_to(APP_DIR)
                violations.append(f"{relative}: {module}")
    assert not violations, "Dipendenze architetturali vietate:\n" + "\n".join(
        violations
    )


def test_domain_does_not_depend_on_outer_layers():
    assert_no_imports(
        python_files("domain"),
        (
            "app.adapters",
            "app.api",
            "app.importers",
            "app.repositories",
            "app.schemas",
            "app.services",
        ),
    )


def test_core_language_does_not_depend_on_legacy_domain_models():
    assert_no_imports(
        python_files("domain", "core_language"),
        (
            "app.domain.assignment_models",
            "app.domain.normalized_models",
            "app.domain.operation_events",
            "app.domain.planning_models",
        ),
    )


def test_conflict_service_consumes_the_core_language_bridge():
    modules = imported_modules(
        APP_DIR / "services" / "conflict_service.py"
    )

    assert "app.domain.core_language" in modules


def test_routers_do_not_access_repositories_directly():
    assert_no_imports(
        python_files("api", "routers"),
        ("app.repositories",),
    )


def test_core_modules_do_not_depend_on_adapters_or_plugins():
    paths = [
        path
        for layer in (
            "core",
            "domain",
            "importers",
            "repositories",
            "schemas",
            "services",
        )
        for path in python_files(layer)
    ]
    assert_no_imports(paths, ("app.adapters", "app.plugins"))


def test_core_configuration_does_not_depend_on_outer_interfaces():
    assert_no_imports(
        python_files("core", "configuration"),
        (
            "app.adapters",
            "app.api",
            "app.plugins",
            "app.schemas",
            "app.services",
        ),
    )


def test_plugins_do_not_depend_on_adapters():
    assert_no_imports(
        python_files("plugins"),
        ("app.adapters",),
    )


def test_amazon_adapter_does_not_depend_on_plugins_or_application_services():
    assert_no_imports(
        python_files("adapters", "amazon"),
        (
            "app.api",
            "app.plugins",
            "app.repositories",
            "app.services",
        ),
    )


def test_generic_normalizer_contains_no_adapter_vocabulary():
    source = (
        APP_DIR
        / "services"
        / "normalization_service.py"
    ).read_text(encoding="utf-8").casefold()
    forbidden = (
        "amazon",
        "station",
        "route",
        "wave",
        "cycle",
        "van_down",
        "driver_no_show",
    )

    assert not {
        term
        for term in forbidden
        if term in source
    }


def test_plugin_domain_does_not_depend_on_outer_plugin_layers():
    assert_no_imports(
        python_files("plugins", "fleet", "domain"),
        (
            "app.plugins.fleet.application",
            "app.plugins.fleet.infrastructure",
            "app.plugins.fleet.interfaces",
        ),
    )


def test_plugin_application_does_not_depend_on_interfaces_or_adapters():
    assert_no_imports(
        python_files("plugins", "fleet", "application"),
        (
            "app.adapters",
            "app.plugins.fleet.interfaces",
        ),
    )


def test_production_services_do_not_use_assignment_compatibility_module():
    paths = [
        path
        for path in python_files("services")
        if path.name != "assignment_service.py"
    ]
    assert_no_imports(
        paths,
        ("app.services.assignment_service",),
    )
