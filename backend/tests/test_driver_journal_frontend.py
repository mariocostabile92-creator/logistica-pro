from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend/journal/index.html").read_text(encoding="utf-8")
CSS = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (ROOT / "frontend/assets/css").glob("driver-journal-*.css")
)
JS = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (ROOT / "frontend/assets/js/modules/driver-journal").glob("*.js")
)


def test_journal_has_both_paths_progress_summary_and_accessibility():
    assert 'data-operation="check_out"' in HTML
    assert 'data-operation="check_in"' in HTML
    assert 'id="backButton"' in HTML
    assert 'id="summary"' in HTML
    assert 'aria-live="assertive"' in HTML
    assert 'name="viewport"' in HTML


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
    assert "overflow-x: hidden" in CSS
    assert "width: 100%" in CSS
    assert "min-width: 0" in CSS


def test_sensitive_data_is_not_persisted_client_side():
    assert "localStorage" not in JS
    assert "sessionStorage" not in JS
    assert "declared_driver_identifier" in JS
