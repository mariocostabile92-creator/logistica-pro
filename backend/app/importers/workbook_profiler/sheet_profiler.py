from typing import Any

from app.importers.workbook_profiler.errors import WorkbookSelectionError
from app.importers.workbook_profiler.header_detector import (
    detect_header_candidates,
)
from app.importers.workbook_profiler.models import (
    ScannedSheet,
    ScannedWorkbook,
    SheetProfile,
)
from app.utils.text_normalizer import normalize_text


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _data_row_count(sheet: ScannedSheet, header_row: int | None) -> int:
    if not header_row:
        return 0
    count = 0
    for row in sheet.rows[header_row:]:
        if sum(_present(value) for value in row) >= 2:
            count += 1
    return count


def _density(sheet: ScannedSheet) -> float:
    rows = sheet.rows[:100]
    if not rows or not sheet.total_columns:
        return 0.0
    present = sum(_present(value) for row in rows for value in row)
    return min(1.0, present / (len(rows) * sheet.total_columns))


def _sheet_name_bonus(name: str, dataset_type: str) -> float:
    normalized = normalize_text(name)
    keywords = (
        ("stato parco", "fleet", "flotta", "mezzi", "asset")
        if dataset_type == "fleet"
        else (
            "planning",
            "operativo",
            "route",
            "rotte",
            "dispatch",
            "turni",
            "driver",
        )
    )
    return 0.12 if any(item in normalized for item in keywords) else 0.0


def profile_sheet(
    sheet: ScannedSheet,
    aliases: dict[str, list[str]],
    dataset_type: str,
    *,
    manual_header_row: int | None = None,
) -> SheetProfile:
    candidates = detect_header_candidates(
        sheet,
        aliases,
        manual_row=manual_header_row,
    )
    selected = candidates[0] if candidates else None
    data_rows = _data_row_count(
        sheet,
        selected.row_index if selected else None,
    )
    populated = sum(
        _present(value)
        for row in sheet.rows[:100]
        for value in row
    )
    formula_ratio = (
        min(1.0, len(sheet.formula_cells) / populated)
        if populated
        else 0.0
    )
    alias_coverage = (
        min(1.0, len(selected.matched_fields) / 4)
        if selected
        else 0.0
    )
    score = (
        (selected.confidence if selected else 0.0) * 0.52
        + alias_coverage * 0.25
        + min(1.0, data_rows / 10) * 0.11
        + _density(sheet) * 0.07
        + _sheet_name_bonus(sheet.name, dataset_type)
        - formula_ratio * 0.07
    )
    score = round(max(0.0, min(1.0, score)), 2)
    ignored = not selected or data_rows == 0 or score < 0.18
    reasons = []
    if selected:
        reasons.append(
            f"intestazione candidata alla riga {selected.row_index}"
        )
    if data_rows:
        reasons.append(f"{data_rows} righe tabellari successive")
    if alias_coverage:
        reasons.append("alias coerenti con il flusso richiesto")
    if formula_ratio > 0.35:
        reasons.append("presenza elevata di formule")
    return SheetProfile(
        name=sheet.name,
        total_rows=sheet.total_rows,
        total_columns=sheet.total_columns,
        score=score,
        reason="; ".join(reasons) or "nessuna tabella affidabile rilevata",
        header_row=selected.row_index if selected else None,
        header_confidence=selected.confidence if selected else 0,
        header_candidates=candidates,
        data_rows=data_rows,
        formula_ratio=round(formula_ratio, 2),
        ignored=ignored,
    )


def profile_sheets(
    workbook: ScannedWorkbook,
    aliases: dict[str, list[str]],
    dataset_type: str,
    *,
    selected_sheet: str | None = None,
    manual_header_row: int | None = None,
) -> tuple[ScannedSheet, SheetProfile, list[SheetProfile]]:
    names = {sheet.name for sheet in workbook.sheets}
    if selected_sheet and selected_sheet not in names:
        raise WorkbookSelectionError(
            "Il foglio selezionato non esiste nel workbook."
        )
    profiles = [
        profile_sheet(
            sheet,
            aliases,
            dataset_type,
            manual_header_row=(
                manual_header_row
                if selected_sheet == sheet.name
                else None
            ),
        )
        for sheet in workbook.sheets
    ]
    if selected_sheet:
        selected_index = next(
            index
            for index, sheet in enumerate(workbook.sheets)
            if sheet.name == selected_sheet
        )
    else:
        selected_index = max(
            range(len(profiles)),
            key=lambda index: (
                profiles[index].score,
                -index,
            ),
        )
        if manual_header_row is not None:
            profiles[selected_index] = profile_sheet(
                workbook.sheets[selected_index],
                aliases,
                dataset_type,
                manual_header_row=manual_header_row,
            )
    return (
        workbook.sheets[selected_index],
        profiles[selected_index],
        profiles,
    )
