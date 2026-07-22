from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from hashlib import sha256
import re
from time import perf_counter
from typing import Any

from app.importers.workbook_profiler.workbook_scanner import scan_workbook
from app.plugins.workforce.application.configuration import (
    workforce_status_configuration,
)
from app.plugins.workforce.domain.models import (
    WorkforceImportPreview,
    WorkforceImportSheet,
    WorkforceMapping,
)
from app.utils.text_normalizer import compact_key, normalize_text


FIELD_ALIASES = {
    "external_identifier": (
        "id", "matricola", "driver id", "resource id", "identificativo",
    ),
    "display_name": (
        "nome", "cognome", "nome cognome", "driver", "autista", "risorsa",
        "lavoratore",
    ),
    "role": ("ruolo", "mansione", "role"),
    "employment_type": (
        "contratto", "tipo contratto", "employment type", "full time", "part time",
        "p time", "percentuale part time",
    ),
    "contract_start": ("inizio contratto", "data assunzione", "contract start"),
    "contract_end": (
        "fine contratto", "scadenza contratto", "contract end", "data cessazione",
    ),
    "weekly_hours": ("ore settimanali", "weekly hours", "ore contratto"),
    "date": ("data", "giorno", "date"),
    "status_code": (
        "stato", "status", "assenza", "disponibilita", "disponibilita giornaliera",
    ),
    "shift_code": ("turno", "codice turno", "shift", "fascia"),
    "start_time": ("inizio turno", "ora inizio", "start time"),
    "end_time": ("fine turno", "ora fine", "end time"),
    "notes": ("note", "annotazioni", "notes"),
    "operational_unit_id": (
        "sede", "deposito", "hub", "unita operativa", "station",
    ),
    "required_resources": ("fabbisogno", "risorse richieste", "required resources"),
    "capabilities": ("capability", "abilitazioni", "competenze"),
}


@dataclass(frozen=True)
class ParsedMember:
    external_identifier: str
    values: dict[str, object]


@dataclass(frozen=True)
class ParsedStatus:
    external_identifier: str
    date: str
    values: dict[str, object]


@dataclass(frozen=True)
class ParsedRequirement:
    date: str
    operational_unit_id: str
    required_resources: int
    required_capabilities: list[str]
    source: str


@dataclass
class ParsedWorkforceWorkbook:
    fingerprint: str
    preview: WorkforceImportPreview
    members: list[ParsedMember] = field(default_factory=list)
    statuses: list[ParsedStatus] = field(default_factory=list)
    requirements: list[ParsedRequirement] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Column:
    index: int
    label: str
    target: str | None
    status: str
    confidence: float
    date_value: str | None = None


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


@lru_cache(maxsize=4096)
def _strict_date_text(text: str) -> str | None:
    if not re.fullmatch(
        r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        text,
    ):
        return None
    for pattern in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
    ):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _strict_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    return _strict_date_text(text)


_NORMALIZED_ALIASES = {
    target: tuple(normalize_text(item) for item in aliases)
    for target, aliases in FIELD_ALIASES.items()
}
_EXACT_ALIAS_TARGETS: dict[str, str] = {}
for _target, _aliases in _NORMALIZED_ALIASES.items():
    for _alias in _aliases:
        _EXACT_ALIAS_TARGETS.setdefault(_alias, _target)


@lru_cache(maxsize=4096)
def _target_for_normalized(normalized: str) -> tuple[str | None, float, str]:
    exact = _EXACT_ALIAS_TARGETS.get(normalized)
    if exact:
        return exact, 0.96, "recognized"
    candidates = [
        target
        for target, aliases in _NORMALIZED_ALIASES.items()
        if any(len(alias) >= 4 and alias in normalized for alias in aliases)
    ]
    if len(candidates) == 1:
        return candidates[0], 0.72, "inferred"
    return None, 0.25, "needs_confirmation"


def _target_for(label: Any) -> tuple[str | None, float, str]:
    normalized = normalize_text(label)
    if not normalized:
        return None, 0.0, "ignored"
    return _target_for_normalized(normalized)


def _header_candidate(rows: list[list[Any]]) -> tuple[int | None, list[Column]]:
    best: tuple[float, int, list[Column]] | None = None
    for row_index, row in enumerate(rows[:100], start=1):
        columns = []
        semantic = 0
        dated = 0
        present = 0
        for index, value in enumerate(row):
            if _present(value):
                present += 1
            date_value = _strict_date(value)
            if date_value:
                target, confidence, status = "date", 0.99, "recognized"
                dated += 1
            else:
                target, confidence, status = _target_for(value)
                semantic += target is not None
            columns.append(
                Column(
                    index=index,
                    label=str(value or f"Colonna {index + 1}"),
                    target=target,
                    status=status,
                    confidence=confidence,
                    date_value=date_value,
                )
            )
        score = semantic * 2.0 + min(dated, 14) * 0.45 + min(present, 20) * 0.03
        if semantic >= 1 and (dated >= 1 or semantic >= 2):
            candidate = (score, -row_index, columns)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best is None:
        return None, []
    return -best[1], best[2]


def _responsibility(name: str, columns: list[Column]) -> str:
    targets = {column.target for column in columns if column.target}
    normalized_name = normalize_text(name)
    if "required_resources" in targets or any(
        term in normalized_name for term in ("fabbisogno", "coverage", "copertura")
    ):
        return "requirements"
    if targets & {"contract_start", "contract_end", "weekly_hours", "employment_type"}:
        return "contracts"
    if any(column.date_value for column in columns) or targets & {"date", "shift_code", "status_code"}:
        return "schedule"
    if targets & {"external_identifier", "display_name", "role"}:
        return "members"
    return "ignored"


def _value(row: list[Any], columns: list[Column], target: str) -> Any:
    for column in columns:
        if column.target == target and column.index < len(row):
            return row[column.index]
    return None


def _status_mapping() -> dict[str, str]:
    values = workforce_status_configuration()
    configured = values.get("external_mappings", {})
    mapping: dict[str, str] = {}
    if isinstance(configured, dict):
        for status, aliases in configured.items():
            if isinstance(aliases, list):
                for alias in aliases:
                    mapping[normalize_text(alias)] = str(status)
    return mapping


def _canonical_status(raw: Any, mapping: dict[str, str]) -> tuple[str, str | None]:
    text = str(raw or "").strip()
    normalized = normalize_text(text)
    if not normalized:
        return "unknown", None
    status = mapping.get(normalized)
    if status:
        shift = text if status in {"available", "scheduled"} else None
        return status, shift
    return "scheduled", text


def _member_identifier(raw_id: Any, display_name: str) -> str:
    explicit = str(raw_id or "").strip()
    if explicit:
        return explicit
    name_tokens = sorted(normalize_text(display_name).split())
    canonical_name = compact_key(" ".join(name_tokens))
    return f"source-{sha256(canonical_name.encode()).hexdigest()[:16]}"


def _capabilities(value: Any) -> list[str]:
    return [
        normalize_text(item).replace(" ", "_")
        for item in re.split(r"[,;|]", str(value or ""))
        if normalize_text(item)
    ]


def _employment_type(value: Any, current: object = None) -> str | None:
    if not _present(value):
        return str(current).strip() if _present(current) else None
    if isinstance(value, (int, float)):
        return "part-time" if float(value) > 0 else "full-time"
    normalized = normalize_text(value)
    try:
        percentage = float(normalized.replace(" ", "."))
    except ValueError:
        percentage = None
    if percentage is not None:
        return "part-time" if percentage > 0 else "full-time"
    if "part time" in normalized:
        return "part-time"
    if "full time" in normalized:
        return "full-time"
    return str(value).strip() or None


def interpret_workforce_workbook(content: bytes, filename: str) -> ParsedWorkforceWorkbook:
    total_started = perf_counter()
    workbook = scan_workbook(
        content,
        filename,
        preserve_formula_metadata=False,
    )
    metrics = dict(workbook.metrics)
    metrics.update({"profile": 0.0, "normalize": 0.0, "validate": 0.0})
    fingerprint = sha256(content).hexdigest()
    status_mapping = _status_mapping()
    members: dict[str, dict[str, object]] = {}
    statuses: dict[tuple[str, str], dict[str, object]] = {}
    requirements: dict[tuple[str, str], ParsedRequirement] = {}
    sheets: list[WorkforceImportSheet] = []
    mappings: list[WorkforceMapping] = []
    excluded_rows = 0
    anomalies: list[str] = []

    for sheet in workbook.sheets:
        profile_started = perf_counter()
        header_row, columns = _header_candidate(sheet.rows)
        responsibility = _responsibility(sheet.name, columns)
        metrics["profile"] += perf_counter() - profile_started
        importable_rows = 0
        sheets.append(
            WorkforceImportSheet(
                name=sheet.name,
                responsibility=responsibility,
                header_row=header_row,
                confidence=(0.9 if responsibility != "ignored" else 0.2),
                importable_rows=0,
            )
        )
        for column in columns:
            mappings.append(
                WorkforceMapping(
                    sheet_name=sheet.name,
                    source_column=column.label,
                    target_field=(
                        f"day:{column.date_value}" if column.date_value else column.target
                    ),
                    confidence=column.confidence,
                    status=column.status,
                )
            )
        if responsibility == "ignored" or header_row is None:
            continue

        normalize_started = perf_counter()
        for excel_row, row in enumerate(sheet.rows[header_row:], start=header_row + 1):
            if sum(_present(value) for value in row) < 2:
                excluded_rows += 1
                continue
            display_name = str(_value(row, columns, "display_name") or "").strip()
            raw_identifier = _value(row, columns, "external_identifier")
            if not display_name and not raw_identifier:
                if responsibility == "requirements":
                    display_name = ""
                else:
                    excluded_rows += 1
                    continue
            identifier = _member_identifier(raw_identifier, display_name) if (display_name or raw_identifier) else ""
            source = f"{sheet.name}:row:{excel_row}"

            if identifier:
                current = members.get(identifier, {})
                weekly_hours = _value(row, columns, "weekly_hours")
                try:
                    weekly_hours = float(weekly_hours) if _present(weekly_hours) else current.get("weekly_hours")
                except (TypeError, ValueError):
                    weekly_hours = current.get("weekly_hours")
                    anomalies.append(f"Ore settimanali non valide in {sheet.name}, riga {excel_row}.")
                members[identifier] = {
                    **current,
                    "external_identifier": identifier,
                    "display_name": display_name or str(current.get("display_name") or identifier),
                    "role": str(_value(row, columns, "role") or current.get("role") or "").strip() or None,
                    "employment_type": _employment_type(
                        _value(row, columns, "employment_type"),
                        current.get("employment_type"),
                    ),
                    "contract_start": _strict_date(_value(row, columns, "contract_start")) or current.get("contract_start"),
                    "contract_end": _strict_date(_value(row, columns, "contract_end")) or current.get("contract_end"),
                    "weekly_hours": weekly_hours,
                    "capabilities": _capabilities(_value(row, columns, "capabilities")) or current.get("capabilities", []),
                    "active": True,
                    "source_reference": source,
                }

            explicit_date = _strict_date(_value(row, columns, "date"))
            raw_status = _value(row, columns, "status_code") or _value(row, columns, "shift_code")
            if identifier and explicit_date and _present(raw_status):
                status, inferred_shift = _canonical_status(raw_status, status_mapping)
                statuses[(identifier, explicit_date)] = {
                    "status_code": status,
                    "availability": status in {"available", "scheduled"},
                    "shift_code": str(_value(row, columns, "shift_code") or inferred_shift or "").strip() or None,
                    "start_time": str(_value(row, columns, "start_time") or "").strip() or None,
                    "end_time": str(_value(row, columns, "end_time") or "").strip() or None,
                    "notes": str(_value(row, columns, "notes") or "").strip() or None,
                    "source_reference": source,
                }

            if identifier:
                for column in columns:
                    if not column.date_value or column.index >= len(row):
                        continue
                    cell = row[column.index]
                    if not _present(cell):
                        continue
                    status, shift = _canonical_status(cell, status_mapping)
                    statuses[(identifier, column.date_value)] = {
                        "status_code": status,
                        "availability": status in {"available", "scheduled"},
                        "shift_code": shift,
                        "start_time": None,
                        "end_time": None,
                        "notes": None,
                        "source_reference": source,
                    }

            required = _value(row, columns, "required_resources")
            requirement_date = explicit_date
            if requirement_date and _present(required):
                try:
                    required_count = int(float(required))
                except (TypeError, ValueError):
                    anomalies.append(f"Fabbisogno non valido in {sheet.name}, riga {excel_row}.")
                else:
                    unit = str(_value(row, columns, "operational_unit_id") or "default").strip()
                    requirements[(requirement_date, unit)] = ParsedRequirement(
                        date=requirement_date,
                        operational_unit_id=unit,
                        required_resources=max(0, required_count),
                        required_capabilities=_capabilities(_value(row, columns, "capabilities")),
                        source=source,
                    )
            importable_rows += 1
        sheets[-1] = sheets[-1].model_copy(update={"importable_rows": importable_rows})
        metrics["normalize"] += perf_counter() - normalize_started

    validate_started = perf_counter()
    dates = sorted({item[1] for item in statuses})
    shift_codes = sorted({str(value.get("shift_code")) for value in statuses.values() if value.get("shift_code")})
    absence_codes = {"holiday", "sickness", "leave", "unavailable"}
    matrix_dates = dates[:14]
    matrix = []
    for identifier, member in list(sorted(members.items()))[:30]:
        matrix.append({
            "workforce_member": member["display_name"],
            **{
                day: statuses.get((identifier, day), {}).get("status_code", "-")
                for day in matrix_dates
            },
        })
    confirmation_columns = sorted({
        f"{item.sheet_name}: {item.source_column}"
        for item in mappings
        if item.status == "needs_confirmation"
    })
    preview = WorkforceImportPreview(
        fingerprint=fingerprint,
        sheets=sheets,
        mappings=mappings,
        people_detected=len(members),
        date_from=dates[0] if dates else None,
        date_to=dates[-1] if dates else None,
        shift_codes=shift_codes,
        contracts_detected=sum(bool(item.get("employment_type") or item.get("contract_end")) for item in members.values()),
        absences_detected=sum(item.get("status_code") in absence_codes for item in statuses.values()),
        excluded_rows=excluded_rows,
        confirmation_columns=confirmation_columns,
        anomalies=anomalies[:50],
        matrix=matrix,
    )
    metrics["validate"] = perf_counter() - validate_started
    metrics["total"] = perf_counter() - total_started
    return ParsedWorkforceWorkbook(
        fingerprint=fingerprint,
        preview=preview,
        members=[ParsedMember(identifier, values) for identifier, values in members.items()],
        statuses=[ParsedStatus(identifier, day, values) for (identifier, day), values in statuses.items()],
        requirements=list(requirements.values()),
        metrics=metrics,
    )
