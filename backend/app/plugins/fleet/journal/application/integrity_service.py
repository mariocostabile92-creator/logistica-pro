from app.core.database import db_session
from app.core.runtime_storage import RuntimeStorageError, safe_relative_key
from app.plugins.fleet.journal.infrastructure import repository
from app.plugins.fleet.journal.infrastructure.storage import media_storage


def report(organization_id: str) -> dict[str, object]:
    records = [row for row in repository.all_media_records() if row.get("organization_id") == organization_id]
    missing_files: list[str] = []
    invalid_keys: list[str] = []
    known_keys: set[str] = set()
    for row in records:
        media_id, raw_key = str(row["id"]), str(row["storage_key"])
        try:
            key = safe_relative_key(raw_key)
            known_keys.add(key)
            if not media_storage.path(key).is_file():
                missing_files.append(media_id)
        except RuntimeStorageError:
            invalid_keys.append(media_id)
    with db_session() as conn:
        broken = conn.execute(
            """SELECT mm.id,
                      CASE WHEN js.id IS NULL THEN 1 ELSE 0 END missing_session,
                      CASE WHEN fa.id IS NULL THEN 1 ELSE 0 END missing_vehicle,
                      CASE WHEN js.organization_id IS NOT NULL AND js.organization_id<>mm.organization_id THEN 1 ELSE 0 END organization_mismatch
               FROM movement_media mm
               LEFT JOIN journal_sessions js ON js.id=mm.session_id
               LEFT JOIN fleet_assets fa ON fa.id=mm.vehicle_id
               WHERE mm.organization_id=?""", (organization_id,)
        ).fetchall()
    physical_keys = media_storage.keys()
    return {
        "organization_id": organization_id,
        "records": len(records),
        "missing_files": sorted(missing_files),
        "orphan_files": sorted(physical_keys - known_keys),
        "invalid_keys": sorted(invalid_keys),
        "missing_sessions": [row["id"] for row in broken if row["missing_session"]],
        "missing_vehicles": [row["id"] for row in broken if row["missing_vehicle"]],
        "organization_mismatches": [row["id"] for row in broken if row["organization_mismatch"]],
    }
