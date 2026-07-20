from datetime import date, datetime, time
from typing import Any

from app.importers.workbook_profiler.models import (
    HeaderCandidate,
    ScannedSheet,
)
from app.utils.text_normalizer import normalize_text


MAX_HEADER_SCAN_ROWS = 100


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _matched_fields(
    values: list[Any],
    normalized_aliases: dict[str, tuple[str, ...]],
) -> set[str]:
    fields = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized_value = normalize_text(value)
        if not normalized_value or len(normalized_value) > 80:
            continue
        padded_value = f" {normalized_value} "
        for field, names in normalized_aliases.items():
            if any(
                (
                    normalized_value == alias
                    or f" {alias} " in padded_value
                )
                for alias in names
            ):
                fields.add(field)
    return fields


def _data_continuity(
    sheet: ScannedSheet,
    row_index: int,
    active_columns: list[int],
) -> float:
    following = sheet.rows[row_index : row_index + 12]
    if not following or not active_columns:
        return 0.0
    minimum = max(1, min(3, round(len(active_columns) * 0.15)))
    coherent = 0
    considered = 0
    for row in following:
        count = sum(
            1
            for column in active_columns
            if column < len(row) and _present(row[column])
        )
        if count:
            considered += 1
            coherent += int(count >= minimum)
    return coherent / considered if considered else 0.0


def _merged_penalty(
    sheet: ScannedSheet,
    row_index: int,
    nonempty: int,
) -> float:
    for min_row, max_row, min_col, max_col in sheet.merged_ranges:
        if min_row <= row_index <= max_row:
            if max_col - min_col + 1 >= max(2, nonempty):
                return 0.25
    return 0.0


def _candidate(
    sheet: ScannedSheet,
    row_index: int,
    normalized_aliases: dict[str, tuple[str, ...]],
    *,
    manual: bool = False,
) -> HeaderCandidate | None:
    if row_index < 1 or row_index > sheet.total_rows:
        return None
    row = sheet.rows[row_index - 1]
    active_columns = [
        index for index, value in enumerate(row) if _present(value)
    ]
    values = [row[index] for index in active_columns]
    nonempty = len(values)
    if not nonempty:
        return None

    text_values = [value for value in values if isinstance(value, str)]
    numeric_or_date = [
        value
        for value in values
        if isinstance(value, (int, float, date, datetime, time))
        and not isinstance(value, bool)
    ]
    text_ratio = len(text_values) / nonempty
    unique_ratio = len(
        {normalize_text(value) or str(value) for value in values}
    ) / nonempty
    fields = _matched_fields(values, normalized_aliases)
    continuity = _data_continuity(sheet, row_index, active_columns)
    count_score = min(1.0, nonempty / 8)
    formula_ratio = sum(
        (row_index, column + 1) in sheet.formula_cells
        for column in active_columns
    ) / nonempty

    score = (
        text_ratio * 0.20
        + unique_ratio * 0.10
        + min(1.0, len(fields) / 3) * 0.35
        + continuity * 0.25
        + count_score * 0.10
    )
    if nonempty == 1:
        score -= 0.40
    score -= (len(numeric_or_date) / nonempty) * 0.25
    score -= formula_ratio * 0.20
    score -= _merged_penalty(sheet, row_index, nonempty)
    confidence = round(max(0.0, min(1.0, score)), 2)

    reasons = []
    if fields:
        reasons.append(f"{len(fields)} concetti compatibili")
    if continuity >= 0.6:
        reasons.append("righe dati continue subito sotto")
    if text_ratio >= 0.7:
        reasons.append("prevalenza di etichette testuali")
    if nonempty == 1:
        reasons.append("riga simile a un titolo")
    if manual:
        reasons.insert(0, "riga selezionata manualmente")
    return HeaderCandidate(
        row_index=row_index,
        confidence=confidence,
        reason="; ".join(reasons) or "struttura debole",
        matched_fields=sorted(fields),
        nonempty_cells=nonempty,
        manually_selected=manual,
    )


def detect_header_candidates(
    sheet: ScannedSheet,
    aliases: dict[str, list[str]],
    *,
    manual_row: int | None = None,
) -> list[HeaderCandidate]:
    normalized_aliases = {
        field: tuple(
            normalized
            for alias in names
            if (normalized := normalize_text(alias))
        )
        for field, names in aliases.items()
    }
    candidates = [
        item
        for row_index in range(
            1,
            min(sheet.total_rows, MAX_HEADER_SCAN_ROWS) + 1,
        )
        if (
            item := _candidate(
                sheet,
                row_index,
                normalized_aliases,
                manual=manual_row == row_index,
            )
        )
    ]
    candidates.sort(
        key=lambda item: (
            item.row_index != manual_row if manual_row else False,
            -item.confidence,
            item.row_index,
        )
    )
    if manual_row is not None:
        selected = next(
            (
                item
                for item in candidates
                if item.row_index == manual_row
            ),
            None,
        )
        return (
            [selected]
            + [item for item in candidates if item is not selected][:4]
            if selected
            else candidates[:5]
        )
    return candidates[:5]
