from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from hashlib import sha256
from decimal import Decimal, InvalidOperation
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
from app.plugins.workforce.domain.driver_shift_contact import (
    normalize_email,
    normalize_phone,
)
from app.plugins.workforce.domain.coverage import (
    CoverageSource,
    ImportedDailyCoverageRequirement,
    required_capacity_for,
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
    "phone": (
        "telefono", "phone", "mobile", "cellulare", "numero telefono",
        "phone number",
    ),
    "email": ("email", "e-mail", "mail", "indirizzo email"),
    "employment_type": (
        "contratto", "tipo contratto", "employment type", "full time", "part time",
        "p time", "percentuale part time",
    ),
    "operational_cycle": (
        "operational cycle", "ciclo operativo", "service cycle", "delivery cycle",
        "next day same day",
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
    "operational_activity": (
        "attivita operativa", "attività operativa", "operational activity", "activity",
    ),
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
    phone: str | None = None
    email: str | None = None
    phone_original: str | None = None
    email_original: str | None = None
    phone_present: bool = False
    email_present: bool = False
    phone_valid: bool = False
    email_valid: bool = False
    phone_invalid: bool = False
    email_invalid: bool = False
    phone_conflict: bool = False
    email_conflict: bool = False


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


@dataclass(frozen=True)
class ParsedWorkforceSourceRow:
    source_sheet: str
    source_row_number: int
    source_reference: str
    source_record_key: str
    row_kind: str
    resolution_identifier: str | None
    source_external_identifier: str | None
    driver_display_name: str | None
    transporter_id: str | None
    station: str | None
    operational_date: str | None
    status_code: str | None
    availability: bool | None
    shift_code: str | None
    operational_activity: str | None
    start_time: str | None
    end_time: str | None
    notes: str | None
    employment_type: str | None
    operational_cycle: str | None
    contract_start: str | None
    contract_end: str | None
    weekly_hours: float | None
    raw_payload: dict[str, object]


@dataclass
class ParsedWorkforceWorkbook:
    fingerprint: str
    preview: WorkforceImportPreview
    members: list[ParsedMember] = field(default_factory=list)
    statuses: list[ParsedStatus] = field(default_factory=list)
    requirements: list[ParsedRequirement] = field(default_factory=list)
    coverage_requirements: list[ImportedDailyCoverageRequirement] = field(
        default_factory=list
    )
    source_rows: list[ParsedWorkforceSourceRow] = field(default_factory=list)
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

_STRICT_ALIAS_TARGETS = {"phone", "email"}


@lru_cache(maxsize=4096)
def _target_for_normalized(normalized: str) -> tuple[str | None, float, str]:
    exact = _EXACT_ALIAS_TARGETS.get(normalized)
    if exact:
        return exact, 0.96, "recognized"
    candidates = [
        target
        for target, aliases in _NORMALIZED_ALIASES.items()
        if target not in _STRICT_ALIAS_TARGETS
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
    if targets & {
        "contract_start", "contract_end", "weekly_hours", "employment_type",
        "operational_cycle",
    }:
        return "contracts"
    if any(column.date_value for column in columns) or targets & {"date", "shift_code", "status_code"}:
        return "schedule"
    if targets & {"external_identifier", "display_name", "role", "phone", "email"}:
        return "members"
    return "ignored"


def _value(row: list[Any], columns: list[Column], target: str) -> Any:
    for column in columns:
        if column.target == target and column.index < len(row):
            return row[column.index]
    return None


TRANSPORTER_ID_ALIASES = {
    "t id", "tid", "transporter id", "transporter external id",
}


def _source_value(
    row: list[Any],
    columns: list[Column],
    aliases: set[str],
) -> Any:
    for column in columns:
        if (
            normalize_text(column.label) in aliases
            and column.index < len(row)
        ):
            return row[column.index]
    return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _raw_payload(**values: Any) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in values.items():
        if not _present(value):
            continue
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
        elif isinstance(value, date):
            payload[key] = value.isoformat()
        elif isinstance(value, (str, int, float, bool)):
            payload[key] = value
        else:
            payload[key] = str(value)
    return payload


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


def _operational_cycle(value: Any) -> tuple[str | None, bool]:
    if not _present(value):
        return None, False
    compact = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    if compact in {"NEXT", "NEXTDAY", "ND"}:
        return "NEXT_DAY", False
    if compact in {"SAMEDAY", "SD", "MATTINO", "POMERIGGIO"}:
        return "SAME_DAY", False
    return None, True


def _source_operational_cycle(
    explicit_value: Any,
    source_shift_group: Any,
) -> tuple[str | None, bool]:
    if _present(explicit_value):
        return _operational_cycle(explicit_value)
    compact = re.sub(r"[^A-Z0-9]", "", str(source_shift_group or "").upper())
    if compact in {"NEXT", "NEXTDAY", "ND"}:
        return "NEXT_DAY", False
    if compact in {"MATTINO", "POMERIGGIO", "SAMEDAY", "SD"}:
        return "SAME_DAY", False
    return None, False


_COVERAGE_LABELS = {
    "forecast": ("NEXT_DAY", None),
    "forecast same day a": ("SAME_DAY", "A"),
    "forecast same day b c": ("SAME_DAY", "B_C"),
}
_DEFAULT_RESERVE_PERCENTAGE = 10


def _excel_column_name(zero_based_index: int) -> str:
    value = zero_based_index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _forecast_routes(value: Any) -> int | None:
    if isinstance(value, bool) or not _present(value):
        return None
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if numeric < 0 or numeric != numeric.to_integral_value():
        return None
    return int(numeric)


def _coverage_requirements(
    sheets: tuple[Any, ...],
    fingerprint: str,
) -> list[ImportedDailyCoverageRequirement]:
    parsed: list[ImportedDailyCoverageRequirement] = []
    for sheet in sheets:
        if normalize_text(sheet.name) != "planning":
            continue
        label_rows: dict[tuple[str, str | None], int] = {}
        for row_index, row in enumerate(sheet.rows[:40]):
            for value in row:
                bucket = _COVERAGE_LABELS.get(normalize_text(value))
                if bucket is not None:
                    label_rows[bucket] = row_index
        if not label_rows:
            continue
        dated_rows: list[tuple[int, dict[int, str]]] = []
        for row_index, row in enumerate(sheet.rows[:50]):
            dates = {
                column_index: normalized
                for column_index, value in enumerate(row)
                if (normalized := _strict_date(value)) is not None
            }
            if dates:
                dated_rows.append((row_index, dates))
        if not dated_rows:
            continue
        _, date_columns = max(dated_rows, key=lambda item: len(item[1]))
        for (cycle, segment), row_index in label_rows.items():
            row = sheet.rows[row_index]
            for column_index, operational_date in date_columns.items():
                if column_index >= len(row):
                    continue
                forecast = _forecast_routes(row[column_index])
                if forecast is None:
                    continue
                source_reference = (
                    f"{sheet.name}!{_excel_column_name(column_index)}{row_index + 1}"
                )
                parsed.append(ImportedDailyCoverageRequirement(
                    operational_date=operational_date,
                    station=None,
                    operational_cycle=cycle,
                    coverage_segment=segment,
                    forecast_routes=forecast,
                    reserve_percentage=_DEFAULT_RESERVE_PERCENTAGE,
                    required_capacity=required_capacity_for(
                        forecast, _DEFAULT_RESERVE_PERCENTAGE
                    ),
                    source=CoverageSource.IMPORT.value,
                    source_reference=source_reference,
                    source_identity=f"import:{fingerprint}",
                ))
    return parsed


def _contact_state() -> dict[str, object]:
    return {
        "phone": None,
        "email": None,
        "phone_original": None,
        "email_original": None,
        "phone_present": False,
        "email_present": False,
        "phone_valid": False,
        "email_valid": False,
        "phone_invalid": False,
        "email_invalid": False,
        "phone_conflict": False,
        "email_conflict": False,
    }


def _merge_contact(
    state: dict[str, object],
    field: str,
    raw_value: Any,
    *,
    source: str,
    identifier: str,
    anomalies: list[str],
) -> None:
    original = _text(raw_value)
    if original is None:
        return
    state[f"{field}_present"] = True
    normalizer = normalize_phone if field == "phone" else normalize_email
    normalized = normalizer(original)
    label = "Telefono" if field == "phone" else "Email"
    if normalized is None:
        state[f"{field}_invalid"] = True
        if not state.get(f"{field}_valid") and not state.get(f"{field}_conflict"):
            state[field] = original
            state[f"{field}_original"] = original
        anomalies.append(
            f"{label} non valido per {identifier} in {source}."
        )
        return
    if state.get(f"{field}_conflict"):
        return
    current = state.get(field) if state.get(f"{field}_valid") else None
    if current is not None and current != normalized:
        state[field] = None
        state[f"{field}_original"] = None
        state[f"{field}_valid"] = False
        state[f"{field}_conflict"] = True
        anomalies.append(
            f"Conflitto {label.lower()} per {identifier}: valori differenti nello stesso file."
        )
        return
    state[field] = normalized
    state[f"{field}_original"] = original
    state[f"{field}_valid"] = True


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
    coverage_requirements = _coverage_requirements(workbook.sheets, fingerprint)
    status_mapping = _status_mapping()
    members: dict[str, dict[str, object]] = {}
    member_contacts: dict[str, dict[str, object]] = {}
    statuses: dict[tuple[str, str], dict[str, object]] = {}
    requirements: dict[tuple[str, str], ParsedRequirement] = {}
    source_rows: list[ParsedWorkforceSourceRow] = []
    sheets: list[WorkforceImportSheet] = []
    mappings: list[WorkforceMapping] = []
    excluded_rows = 0
    anomalies: list[str] = []
    operational_cycle_invalid = 0
    operational_cycle_conflicts: set[str] = set()

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
            transporter_id = _text(
                _source_value(row, columns, TRANSPORTER_ID_ALIASES)
            )
            if not display_name and not raw_identifier and not transporter_id:
                if responsibility == "requirements":
                    display_name = ""
                else:
                    excluded_rows += 1
                    continue
            identifier = _member_identifier(raw_identifier, display_name) if (display_name or raw_identifier) else ""
            source = f"{sheet.name}:row:{excel_row}"
            source_external_identifier = _text(raw_identifier)
            if identifier:
                contact = member_contacts.setdefault(identifier, _contact_state())
                _merge_contact(
                    contact,
                    "phone",
                    _value(row, columns, "phone"),
                    source=source,
                    identifier=identifier,
                    anomalies=anomalies,
                )
                _merge_contact(
                    contact,
                    "email",
                    _value(row, columns, "email"),
                    source=source,
                    identifier=identifier,
                    anomalies=anomalies,
                )
            station = _text(_value(row, columns, "operational_unit_id"))
            employment_type = _employment_type(
                _value(row, columns, "employment_type")
            )
            operational_cycle, cycle_invalid = _source_operational_cycle(
                _value(row, columns, "operational_cycle"),
                _value(row, columns, "shift_code"),
            )
            if cycle_invalid:
                operational_cycle_invalid += 1
                anomalies.append(
                    f"Ciclo operativo non riconosciuto in {sheet.name}, riga {excel_row}."
                )
            contract_start = _strict_date(
                _value(row, columns, "contract_start")
            )
            contract_end = _strict_date(
                _value(row, columns, "contract_end")
            )
            raw_weekly_hours = _value(row, columns, "weekly_hours")
            try:
                source_weekly_hours = (
                    float(raw_weekly_hours)
                    if _present(raw_weekly_hours)
                    else None
                )
            except (TypeError, ValueError):
                source_weekly_hours = None

            if identifier or transporter_id:
                source_rows.append(ParsedWorkforceSourceRow(
                    source_sheet=sheet.name,
                    source_row_number=excel_row,
                    source_reference=source,
                    source_record_key="identity",
                    row_kind="identity",
                    resolution_identifier=identifier or None,
                    source_external_identifier=source_external_identifier,
                    driver_display_name=display_name or None,
                    transporter_id=transporter_id,
                    station=station,
                    operational_date=None,
                    status_code=None,
                    availability=None,
                    shift_code=None,
                    operational_activity=None,
                    start_time=None,
                    end_time=None,
                    notes=_text(_value(row, columns, "notes")),
                    employment_type=employment_type,
                    operational_cycle=operational_cycle,
                    contract_start=contract_start,
                    contract_end=contract_end,
                    weekly_hours=source_weekly_hours,
                    raw_payload=_raw_payload(
                        source_external_identifier=raw_identifier,
                        driver_display_name=display_name,
                        transporter_id=transporter_id,
                        station=station,
                        employment_type=_value(
                            row, columns, "employment_type"
                        ),
                        operational_cycle=_value(row, columns, "operational_cycle"),
                        contract_start=_value(
                            row, columns, "contract_start"
                        ),
                        contract_end=_value(row, columns, "contract_end"),
                        weekly_hours=raw_weekly_hours,
                        notes=_value(row, columns, "notes"),
                    ),
                ))

            if identifier:
                current = members.get(identifier, {})
                current_cycle = current.get("operational_cycle")
                if operational_cycle and current_cycle and operational_cycle != current_cycle:
                    operational_cycle_conflicts.add(identifier)
                    anomalies.append(
                        f"Conflitto ciclo operativo per {identifier}: NEXT_DAY e SAME_DAY nello stesso file."
                    )
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
                    "operational_cycle": (
                        None
                        if identifier in operational_cycle_conflicts
                        else operational_cycle or current_cycle
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
            if (identifier or transporter_id) and explicit_date and _present(raw_status):
                status, inferred_shift = _canonical_status(raw_status, status_mapping)
                status_values = {
                    "status_code": status,
                    "availability": status in {"available", "available_limited", "scheduled"},
                    "shift_code": str(_value(row, columns, "shift_code") or inferred_shift or "").strip() or None,
                    "operational_activity": _text(_value(row, columns, "operational_activity")),
                    "start_time": str(_value(row, columns, "start_time") or "").strip() or None,
                    "end_time": str(_value(row, columns, "end_time") or "").strip() or None,
                    "notes": str(_value(row, columns, "notes") or "").strip() or None,
                    "source_reference": source,
                }
                if identifier:
                    statuses[(identifier, explicit_date)] = status_values
                source_rows.append(ParsedWorkforceSourceRow(
                    source_sheet=sheet.name,
                    source_row_number=excel_row,
                    source_reference=source,
                    source_record_key=f"shift:{explicit_date}:explicit",
                    row_kind="shift",
                    resolution_identifier=identifier or None,
                    source_external_identifier=source_external_identifier,
                    driver_display_name=display_name or None,
                    transporter_id=transporter_id,
                    station=station,
                    operational_date=explicit_date,
                    status_code=status_values["status_code"],
                    availability=status_values["availability"],
                    shift_code=status_values["shift_code"],
                    operational_activity=status_values["operational_activity"],
                    start_time=status_values["start_time"],
                    end_time=status_values["end_time"],
                    notes=status_values["notes"],
                    employment_type=employment_type,
                    operational_cycle=operational_cycle,
                    contract_start=contract_start,
                    contract_end=contract_end,
                    weekly_hours=source_weekly_hours,
                    raw_payload=_raw_payload(
                        source_external_identifier=raw_identifier,
                        driver_display_name=display_name,
                        transporter_id=transporter_id,
                        station=station,
                        operational_date=explicit_date,
                        source_status_or_shift=raw_status,
                        source_shift_code=_value(row, columns, "shift_code"),
                        operational_activity=_value(row, columns, "operational_activity"),
                        start_time=_value(row, columns, "start_time"),
                        end_time=_value(row, columns, "end_time"),
                        notes=_value(row, columns, "notes"),
                    ),
                ))

            if identifier or transporter_id:
                for column in columns:
                    if not column.date_value or column.index >= len(row):
                        continue
                    cell = row[column.index]
                    if not _present(cell):
                        continue
                    status, shift = _canonical_status(cell, status_mapping)
                    status_values = {
                        "status_code": status,
                        "availability": status in {"available", "available_limited", "scheduled"},
                        "shift_code": shift,
                        "operational_activity": None,
                        "start_time": None,
                        "end_time": None,
                        "notes": None,
                        "source_reference": source,
                    }
                    if identifier:
                        statuses[(identifier, column.date_value)] = status_values
                    source_rows.append(ParsedWorkforceSourceRow(
                        source_sheet=sheet.name,
                        source_row_number=excel_row,
                        source_reference=source,
                        source_record_key=(
                            f"shift:{column.date_value}:column:{column.index}"
                        ),
                        row_kind="shift",
                        resolution_identifier=identifier or None,
                        source_external_identifier=source_external_identifier,
                        driver_display_name=display_name or None,
                        transporter_id=transporter_id,
                        station=station,
                        operational_date=column.date_value,
                        status_code=status_values["status_code"],
                        availability=status_values["availability"],
                        shift_code=status_values["shift_code"],
                        operational_activity=None,
                        start_time=None,
                        end_time=None,
                        notes=None,
                        employment_type=employment_type,
                        operational_cycle=operational_cycle,
                        contract_start=contract_start,
                        contract_end=contract_end,
                        weekly_hours=source_weekly_hours,
                        raw_payload=_raw_payload(
                            source_external_identifier=raw_identifier,
                            driver_display_name=display_name,
                            transporter_id=transporter_id,
                            station=station,
                            operational_date=column.date_value,
                            source_status_or_shift=cell,
                        ),
                    ))

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
    phone_detected = sum(
        bool(item["phone_valid"]) and not bool(item["phone_conflict"])
        for item in member_contacts.values()
    )
    email_detected = sum(
        bool(item["email_valid"]) and not bool(item["email_conflict"])
        for item in member_contacts.values()
    )
    invalid_contacts = sum(
        bool(item["phone_invalid"]) + bool(item["email_invalid"])
        for item in member_contacts.values()
    )
    contact_conflicts = sum(
        bool(item["phone_conflict"]) + bool(item["email_conflict"])
        for item in member_contacts.values()
    )
    preview = WorkforceImportPreview(
        fingerprint=fingerprint,
        sheets=sheets,
        mappings=mappings,
        people_detected=len(members),
        date_from=dates[0] if dates else None,
        date_to=dates[-1] if dates else None,
        shift_codes=shift_codes,
        contracts_detected=sum(bool(item.get("employment_type") or item.get("contract_end")) for item in members.values()),
        next_day_detected=sum(item.get("operational_cycle") == "NEXT_DAY" for item in members.values()),
        same_day_detected=sum(item.get("operational_cycle") == "SAME_DAY" for item in members.values()),
        operational_cycle_unrecognized=(operational_cycle_invalid + len(operational_cycle_conflicts)),
        coverage_requirements_detected=len(coverage_requirements),
        absences_detected=sum(item.get("status_code") in absence_codes for item in statuses.values()),
        excluded_rows=excluded_rows,
        confirmation_columns=confirmation_columns,
        phone_detected=phone_detected,
        email_detected=email_detected,
        invalid_contacts=invalid_contacts,
        contact_conflicts=contact_conflicts,
        anomalies=anomalies[:50],
        matrix=matrix,
    )
    metrics["validate"] = perf_counter() - validate_started
    metrics["total"] = perf_counter() - total_started
    return ParsedWorkforceWorkbook(
        fingerprint=fingerprint,
        preview=preview,
        members=[
            ParsedMember(
                identifier,
                values,
                **member_contacts.get(identifier, _contact_state()),
            )
            for identifier, values in members.items()
        ],
        statuses=[ParsedStatus(identifier, day, values) for (identifier, day), values in statuses.items()],
        requirements=list(requirements.values()),
        coverage_requirements=coverage_requirements,
        source_rows=source_rows,
        metrics=metrics,
    )
