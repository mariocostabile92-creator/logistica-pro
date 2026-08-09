import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.importers.workbook_profiler.models import ScannedSheet


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


TRANSPORTER_ALIASES = {
    "t id", "tid", "transporter id", "transporter", "transporter external id",
}
DRIVER_NAME_ALIASES = {
    "driver", "drivers", "driver name", "nome driver", "delivery associate", "da name",
}
WORKFORCE_EXTERNAL_ALIASES = {
    "external identifier", "external id", "workforce external identifier",
    "workforce identifier", "driver id", "driver external id",
}
WORKFORCE_MEMBER_ALIASES = {
    "workforce member id", "workforce_member_id", "member id",
}


@dataclass(frozen=True)
class IdentitySourceSelection:
    sheet: str | None = None
    transporter_column: str | None = None
    driver_column: str | None = None


@dataclass(frozen=True)
class IdentitySourceRow:
    transporter_external_id: str
    source_driver_identifier: str
    driver_identifier_kind: str
    source_sheet: str
    source_row: int


@dataclass(frozen=True)
class IdentitySourceDetection:
    status: str
    sheet: str | None = None
    header_row: int | None = None
    transporter_column: str | None = None
    driver_column: str | None = None
    driver_identifier_kind: str | None = None
    candidate_sheets: list[str] = field(default_factory=list)
    transporter_candidates: list[str] = field(default_factory=list)
    driver_candidates: list[str] = field(default_factory=list)
    rows: list[IdentitySourceRow] = field(default_factory=list)


def _header_candidates(sheet: ScannedSheet) -> list[dict]:
    candidates = []
    for row_index, row in enumerate(sheet.rows, start=1):
        headers = [str(value or "").strip() for value in row]
        transporter = [header for header in headers if _key(header) in TRANSPORTER_ALIASES]
        names = [header for header in headers if _key(header) in DRIVER_NAME_ALIASES]
        external = [header for header in headers if _key(header) in WORKFORCE_EXTERNAL_ALIASES]
        members = [header for header in headers if _key(header) in WORKFORCE_MEMBER_ALIASES]
        drivers = [*members, *external, *names]
        if not transporter and drivers:
            for column, header in enumerate(headers):
                if _key(header) != "da id":
                    continue
                values = [
                    str(item[column]).strip()
                    for item in sheet.rows[row_index:row_index + 50]
                    if column < len(item) and str(item[column] or "").strip()
                ]
                if values and sum(bool(re.fullmatch(r"A[A-Z0-9]{8,}", value.upper())) for value in values) / len(values) >= 0.8:
                    transporter.append(header)
        if transporter and drivers:
            candidates.append({
                "row_index": row_index,
                "headers": headers,
                "transporter": transporter,
                "drivers": drivers,
                "member": members,
                "external": external,
                "name": names,
            })
    return candidates


def _kind(candidate: dict, column: str) -> str:
    if column in candidate["member"]:
        return "workforce_member_id"
    if column in candidate["external"]:
        return "external_identifier"
    return "display_name"


def detect_identity_source(
    sheets: tuple[ScannedSheet, ...],
    selection: IdentitySourceSelection | None = None,
) -> IdentitySourceDetection:
    selection = selection or IdentitySourceSelection()
    sheet_candidates = {
        sheet.name: _header_candidates(sheet)
        for sheet in sheets
    }
    valid_sheets = [name for name, candidates in sheet_candidates.items() if candidates]
    if selection.sheet:
        valid_sheets = [name for name in valid_sheets if name == selection.sheet]
    if not valid_sheets:
        return IdentitySourceDetection(status="NO_VALID_SCHEMA")
    if len(valid_sheets) > 1 and not selection.sheet:
        return IdentitySourceDetection(
            status="AMBIGUOUS_SCHEMA",
            candidate_sheets=valid_sheets,
        )
    sheet_name = valid_sheets[0]
    candidates = sheet_candidates[sheet_name]
    if len(candidates) > 1:
        exact = [
            item for item in candidates
            if selection.transporter_column in item["transporter"]
            and selection.driver_column in item["drivers"]
        ]
        if len(exact) != 1:
            return IdentitySourceDetection(
                status="AMBIGUOUS_SCHEMA",
                sheet=sheet_name,
                candidate_sheets=valid_sheets,
                transporter_candidates=sorted({value for item in candidates for value in item["transporter"]}),
                driver_candidates=sorted({value for item in candidates for value in item["drivers"]}),
            )
        candidate = exact[0]
    else:
        candidate = candidates[0]

    transporter_columns = candidate["transporter"]
    driver_columns = candidate["drivers"]
    transporter_column = selection.transporter_column or (
        transporter_columns[0] if len(transporter_columns) == 1 else None
    )
    driver_column = selection.driver_column or (
        driver_columns[0] if len(driver_columns) == 1 else None
    )
    if transporter_column not in transporter_columns or driver_column not in driver_columns:
        return IdentitySourceDetection(
            status="AMBIGUOUS_SCHEMA",
            sheet=sheet_name,
            header_row=candidate["row_index"],
            candidate_sheets=valid_sheets,
            transporter_candidates=transporter_columns,
            driver_candidates=driver_columns,
        )

    sheet = next(item for item in sheets if item.name == sheet_name)
    transporter_index = candidate["headers"].index(transporter_column)
    driver_index = candidate["headers"].index(driver_column)
    kind = _kind(candidate, driver_column)
    rows = []
    for source_row, values in enumerate(
        sheet.rows[candidate["row_index"]:],
        start=candidate["row_index"] + 1,
    ):
        transporter = str(values[transporter_index] if transporter_index < len(values) else "").strip()
        driver = str(values[driver_index] if driver_index < len(values) else "").strip()
        if not transporter:
            continue
        rows.append(IdentitySourceRow(
            transporter_external_id=transporter,
            source_driver_identifier=driver,
            driver_identifier_kind=kind,
            source_sheet=sheet_name,
            source_row=source_row,
        ))
    return IdentitySourceDetection(
        status="READY",
        sheet=sheet_name,
        header_row=candidate["row_index"],
        transporter_column=transporter_column,
        driver_column=driver_column,
        driver_identifier_kind=kind,
        candidate_sheets=valid_sheets,
        transporter_candidates=transporter_columns,
        driver_candidates=driver_columns,
        rows=rows,
    )
