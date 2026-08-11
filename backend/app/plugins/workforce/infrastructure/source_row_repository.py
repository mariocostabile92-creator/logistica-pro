import json

from app.core.database import db_session
from app.plugins.workforce.domain.import_rows import WorkforceImportRow


def _row(item) -> WorkforceImportRow:
    values = {key: item[key] for key in item.keys()}
    values["availability"] = (
        bool(values["availability"])
        if values["availability"] is not None
        else None
    )
    values["raw_payload"] = json.loads(values["raw_payload"] or "{}")
    return WorkforceImportRow.model_validate(values)


def _list(
    organization_id: str,
    workforce_import_id: int,
    *,
    identity_only: bool,
) -> list[WorkforceImportRow]:
    condition = "AND r.row_kind = 'identity'" if identity_only else ""
    with db_session() as conn:
        rows = conn.execute(
            f"""
            SELECT r.*, i.original_filename AS source_filename,
                   i.imported_at
            FROM workforce_import_rows r
            JOIN workforce_imports i ON i.id = r.workforce_import_id
            WHERE r.organization_id = ?
              AND i.organization_id = ?
              AND r.workforce_import_id = ?
              {condition}
            ORDER BY r.source_sheet, r.source_row_number,
                     r.source_record_key, r.id
            """,
            (organization_id, organization_id, workforce_import_id),
        ).fetchall()
    return [_row(item) for item in rows]


def list_import_rows(
    organization_id: str,
    workforce_import_id: int,
) -> list[WorkforceImportRow]:
    return _list(
        organization_id,
        workforce_import_id,
        identity_only=False,
    )


def list_import_identity_rows(
    organization_id: str,
    workforce_import_id: int,
) -> list[WorkforceImportRow]:
    return _list(
        organization_id,
        workforce_import_id,
        identity_only=True,
    )
