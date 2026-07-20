import re
from datetime import date, datetime
from typing import Any

from app.importers.workbook_profiler.models import (
    HeaderCandidate,
    ScannedSheet,
    ScannedWorkbook,
    WorkbookClassification,
    WorkbookType,
)
from app.utils.text_normalizer import normalize_text


WORKFORCE_TERMS = {
    "ferie",
    "riposo",
    "malattia",
    "contratto",
    "full time",
    "part time",
    "turni",
    "assenza",
    "lunedi",
    "martedi",
    "mercoledi",
    "giovedi",
    "venerdi",
    "sabato",
    "domenica",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

FLEET_TERMS = {
    "targa",
    "modello",
    "disponibilita",
    "noleggio",
    "stato",
    "officina",
    "danno",
    "documento",
    "parcheggio",
    "carta carburante",
    "fuel",
}


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _term_hits(
    workbook: ScannedWorkbook,
    terms: set[str],
) -> set[str]:
    hits = set()
    for sheet in workbook.sheets:
        sheet_name = normalize_text(sheet.name)
        for term in terms - hits:
            if (
                sheet_name == term
                or f" {term} " in f" {sheet_name} "
            ):
                hits.add(term)
        for row in sheet.rows[:100]:
            for value in row:
                if not isinstance(value, str):
                    continue
                normalized = normalize_text(value)
                padded = f" {normalized} "
                for term in terms - hits:
                    if normalized == term or f" {term} " in padded:
                        hits.add(term)
    return hits


def _calendar_columns(
    sheet: ScannedSheet,
    header: HeaderCandidate | None,
) -> int:
    if not header:
        return 0
    values = sheet.rows[header.row_index - 1]
    total = 0
    for value in values:
        if isinstance(value, (date, datetime)):
            total += 1
            continue
        normalized = normalize_text(value)
        if (
            re.fullmatch(r"\d{1,2}\s+\d{1,2}(?:\s+\d{2,4})?", normalized)
            or normalized in WORKFORCE_TERMS
        ):
            total += 1
    return total


def classify_workbook(
    workbook: ScannedWorkbook,
    selected_sheet: ScannedSheet,
    header: HeaderCandidate | None,
    confirmed_fields: set[str] | None = None,
) -> WorkbookClassification:
    native_fields = set(header.matched_fields if header else [])
    fields = native_fields | (confirmed_fields or set())
    workforce_hits = _term_hits(workbook, WORKFORCE_TERMS)
    fleet_hits = _term_hits(workbook, FLEET_TERMS)
    calendar_columns = _calendar_columns(selected_sheet, header)

    workforce_score = min(
        1.0,
        len(workforce_hits) * 0.10
        + (0.35 if calendar_columns >= 3 else 0)
        + (
            0.15
            if any(
                term in normalize_text(selected_sheet.name)
                for term in ("turni", "part time", "workforce")
            )
            else 0
        )
        + (
            0.30
            if selected_sheet.total_columns >= 30
            and workforce_hits
            else 0
        ),
    )
    daily_required = {"route", "station", "driver_name"}
    daily_score = 0.0
    if daily_required <= fields:
        daily_score = 0.78
        daily_score += 0.08 if "cycle" in fields else 0
        daily_score += 0.05 if "vehicle_plate" in fields else 0

    fleet_score = 0.0
    if "vehicle_plate" in fields:
        supporting_fields = fields & {
            "driver_name",
            "second_driver_name",
            "status",
            "station",
            "workshop",
            "notes",
            "fuel_card",
            "vehicle_model",
            "expirations",
        }
        fleet_score = (
            0.45
            + min(0.30, len(supporting_fields) * 0.10)
            + min(0.15, len(fleet_hits) * 0.03)
        )
        if "stato parco" in normalize_text(selected_sheet.name):
            fleet_score += 0.10
        fleet_score = min(1.0, fleet_score)

    if (
        workforce_score >= 0.50
        and not daily_required <= native_fields
    ):
        return WorkbookClassification(
            workbook_type=WorkbookType.WORKFORCE_SCHEDULE,
            confidence=round(workforce_score, 2),
            reason=(
                "Rilevati indicatori di turnistica, calendario, "
                "assenze o condizioni contrattuali."
            ),
        )
    if daily_score >= 0.72:
        return WorkbookClassification(
            workbook_type=WorkbookType.DAILY_OPERATIONAL_PLANNING,
            confidence=round(daily_score, 2),
            reason=(
                "Rilevati Task/rotte, Operational Unit/station e "
                "Human Resource/driver nella stessa tabella."
            ),
        )
    if fleet_score >= 0.62:
        return WorkbookClassification(
            workbook_type=WorkbookType.FLEET_REGISTRY,
            confidence=round(fleet_score, 2),
            reason=(
                "Rilevati identificativi Asset e attributi coerenti "
                "con anagrafica o stato del parco."
            ),
        )
    if workforce_score >= 0.50:
        return WorkbookClassification(
            workbook_type=WorkbookType.WORKFORCE_SCHEDULE,
            confidence=round(workforce_score, 2),
            reason=(
                "Rilevati indicatori di turnistica, calendario, "
                "assenze o condizioni contrattuali."
            ),
        )
    return WorkbookClassification(
        workbook_type=WorkbookType.UNKNOWN_WORKBOOK,
        confidence=round(
            max(daily_score, fleet_score, workforce_score, 0.2),
            2,
        ),
        reason=(
            "Non sono presenti insieme abbastanza concetti per "
            "identificare un Planning operativo, una turnistica "
            "o un registro Fleet."
        ),
    )
