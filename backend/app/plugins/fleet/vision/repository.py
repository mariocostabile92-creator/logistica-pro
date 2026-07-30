import json

from app.core.database import db_session


def snapshot() -> dict[str, list[dict]]:
    queries = {
        "assets": """
            SELECT a.id, a.external_identifier, a.plate, a.category AS vehicle_model,
                   a.availability, a.updated_at, p.contract_type,
                   p.company, p.contract_number
            FROM fleet_assets a
            LEFT JOIN fleet_asset_profiles p ON p.asset_id = a.id
            ORDER BY COALESCE(a.plate,a.external_identifier)
        """,
        "movements": """
            SELECT asset_id, id, operation_type, occurred_at,
                   declared_driver_identifier, odometer_km
            FROM asset_movements
        """,
        "damages": """
            SELECT vehicle_id, id, case_number, status, severity,
                   description, occurred_at, created_at, closed_at
            FROM damage_cases
        """,
        "maintenances": """
            SELECT vehicle_id, id, maintenance_number, status,
                   maintenance_type, description, opened_at, expected_at,
                   completed_at, created_at
            FROM fleet_maintenances
        """,
        "documents": """
            SELECT vehicle_id, id, document_type, title, status,
                   expires_at, created_at,
                   (SELECT COUNT(*) FROM attachments a
                    WHERE a.entity_type = 'document'
                      AND a.entity_id = fleet_vehicle_documents.id) AS attachment_count
            FROM fleet_vehicle_documents
        """,
        "insurance": """
            SELECT vehicle_id, id, company, policy_number, coverage_type,
                   expires_on, status FROM fleet_insurance_policies
        """,
        "franchises": """
            SELECT vehicle_id, id, status, created_at, updated_at
            FROM fleet_franchise_cases
        """,
        "rentals": """
            SELECT vehicle_id, id, status, replacement_vehicle,
                   rental_company, start_date, expected_end_date, end_date,
                   created_at
            FROM fleet_rentals WHERE vehicle_id IS NOT NULL
        """,
        "events": """
            SELECT asset_id, occurred_at, details FROM fleet_asset_events
            WHERE event_type = 'operational_status_changed'
            ORDER BY id DESC
        """,
    }
    with db_session() as conn:
        result = {
            name: [{key: row[key] for key in row.keys()} for row in conn.execute(sql).fetchall()]
            for name, sql in queries.items()
        }
    seen: set[int] = set()
    latest = []
    for event in result["events"]:
        if event["asset_id"] in seen:
            continue
        seen.add(event["asset_id"])
        event["details"] = json.loads(event["details"])
        latest.append(event)
    result["events"] = latest
    return result
