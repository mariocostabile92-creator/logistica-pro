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
    assert 'id="startButton"' in HTML
    assert 'id="driverName"' in HTML
    assert 'id="driverSurname"' in HTML
    assert "<h1" in HTML and "Giornale di bordo</h1>" in HTML
    assert 'class="workspace-tabs"' not in HTML
    assert "Planning" not in HTML


def test_frontend_prevents_double_tap_and_handles_api_errors():
    assert "state.submitting" in JS
    assert "if (!response.ok)" in JS
    assert "showError(error.message)" in JS


def test_photo_upload_and_removal_are_real():
    assert 'accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime"' in HTML
    assert "uploadMedia(" in JS
    assert "deleteMedia(" in JS


def test_390px_layout_has_no_horizontal_overflow_contract():
    assert "@media (max-width: 480px)" in CSS
    assert "@media (max-width: 768px)" in CSS
    assert "grid-template-columns: 1fr" in CSS
    assert "min-width: 0" in CSS
    assert ".journal-mobile-context" in CSS


def test_journal_reuses_core_design_tokens_in_a_standalone_driver_shell():
    for stylesheet in (
        "../assets/css/base.css",
        "../assets/css/components.css",
    ):
        assert f'href="{stylesheet}"' in HTML
    assert 'class="journal-driver-header"' in HTML
    assert 'class="journal-workspace"' in HTML
    for office_item in ("Planning", "Workforce", "Fleet", "Learn"):
        assert office_item not in HTML


def test_sensitive_data_is_not_persisted_client_side():
    assert "localStorage" not in JS
    assert "sessionStorage" not in JS
    assert "declared_driver_identifier" in JS
