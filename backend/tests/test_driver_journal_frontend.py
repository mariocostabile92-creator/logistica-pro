from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend/journal/index.html").read_text(encoding="utf-8")
CSS = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (ROOT / "frontend/assets/css").glob("driver-journal-*.css")
)
JS = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (
        ROOT / "frontend/assets/js/modules/driver-journal"
    ).glob("*.js")
)


def test_journal_has_both_paths_progress_summary_and_accessibility():
    assert 'data-operation="check_out"' in HTML
    assert 'data-operation="check_in"' in HTML
    assert 'id="backButton"' in HTML
    assert 'id="summary"' in HTML
    assert 'aria-live="assertive"' in HTML
    assert 'name="viewport"' in HTML
    assert "<h1>Operations Engine</h1>" in HTML
    assert "Fleet Operations" in HTML
    assert "<h2>Giornale di bordo</h2>" in HTML
    navigation = HTML.split('<nav class="workspace-tabs"', 1)[1].split(
        "</nav>", 1
    )[0]
    assert 'href="/app/journal/"' not in navigation
    assert "Giornale di bordo" not in navigation


def test_frontend_prevents_double_tap_and_handles_api_errors():
    assert "state.submitting" in JS
    assert "if (!response.ok)" in JS
    assert "showError(error.message)" in JS


def test_photo_upload_and_removal_are_real():
    assert 'accept="image/jpeg,image/png,image/webp"' in HTML
    assert "uploadMedia(" in JS
    assert "deleteMedia(" in JS


def test_390px_layout_has_no_horizontal_overflow_contract():
    assert "@media (max-width: 480px)" in CSS
    assert "@media (max-width: 768px)" in CSS
    assert "grid-template-columns: 1fr" in CSS
    assert "min-width: 0" in CSS
    assert ".journal-mobile-context" in CSS


def test_journal_reuses_operations_engine_design_system_and_shell():
    for stylesheet in (
        "../assets/css/base.css",
        "../assets/css/layout.css",
        "../assets/css/components.css",
        "../assets/css/responsive.css?v=3",
        "../assets/css/workspace-lifecycle.css?v=5",
    ):
        assert f'href="{stylesheet}"' in HTML
    for item in (
        "Home",
        "Planning",
        "Workforce",
        "Fleet",
        "Learn",
    ):
        assert item in HTML


def test_sensitive_data_is_not_persisted_client_side():
    assert "localStorage" not in JS
    assert "sessionStorage" not in JS
    assert "declared_driver_identifier" in JS
