import json

from app.auth.tenant_context import current_organization_id
from app.core.database import db_session


def snapshot(organization_id: str | None = None) -> dict[str, list[dict]]:
    organization_id = organization_id or current_organization_id()
    queries = {
        "assets": """
            SELECT a.id, a.external_identifier, a.plate, a.category AS vehicle_model,
                   a.availability, a.updated_at, p.contract_type,
                   p.company, p.contract_number
            FROM fleet_assets a
            LEFT JOIN fleet_asset_profiles p ON p.asset_id = a.id
            WHERE a.organization_id = ?
            ORDER BY COALESCE(a.plate,a.external_identifier)
        """,
        "movements": f"""
            SELECT m.asset_id, m.id, m.operation_type, m.occurred_at,
                   m.declared_driver_identifier, m.odometer_km, m.anomaly_present,
                   s.operational_date
            FROM asset_movements m
            JOIN journal_sessions s ON s.id = m.session_id
            WHERE m.organization_id = ?
        """,
        "damages": """
            SELECT d.vehicle_id, d.id, d.case_number, d.status, d.severity,
                   d.description, d.occurred_at, d.created_at, d.closed_at
            FROM damage_cases d
            JOIN fleet_assets a ON a.id=d.vehicle_id
            WHERE a.organization_id = ?
        """,
        "maintenances": """
            SELECT m.vehicle_id, m.id, m.maintenance_number, m.status,
                   m.maintenance_type, m.description, m.opened_at, m.expected_at,
                   m.completed_at, m.created_at
            FROM fleet_maintenances m
            JOIN fleet_assets a ON a.id=m.vehicle_id
            WHERE a.organization_id = ?
        """,
        "documents": """
            SELECT vehicle_id, id, document_type, title, status,
                   expires_at, created_at, archived_at,
                   (SELECT COUNT(*) FROM attachments a
                    WHERE a.entity_type = 'document'
                      AND a.entity_id = fleet_vehicle_documents.id
                      AND a.organization_id = ?) AS attachment_count
            FROM fleet_vehicle_documents
            WHERE organization_id = ?
        """,
        "insurance": """
            SELECT p.vehicle_id, p.id, p.company, p.policy_number, p.coverage_type,
                   p.expires_on, p.status
            FROM fleet_insurance_policies p
            JOIN fleet_assets a ON a.id=p.vehicle_id
            WHERE a.organization_id = ?
        """,
        "franchises": """
            SELECT f.vehicle_id, f.id, f.status, f.created_at, f.updated_at
            FROM fleet_franchise_cases f
            JOIN fleet_assets a ON a.id=f.vehicle_id
            WHERE a.organization_id = ?
        """,
        "rentals": """
            SELECT vehicle_id, id, status, replacement_vehicle,
                   rental_company, start_date, expected_end_date, end_date,
                   created_at
            FROM fleet_rentals
            WHERE vehicle_id IS NOT NULL AND organization_id = ?
        """,
        "events": """
            SELECT e.asset_id, e.occurred_at, e.details
            FROM fleet_asset_events e
            JOIN fleet_assets a ON a.id=e.asset_id
            WHERE e.event_type = 'operational_status_changed'
              AND a.organization_id = ?
            ORDER BY e.id DESC
        """,
    }
    with db_session() as conn:
        result = {}
        for name, sql in queries.items():
            params = (
                (organization_id, organization_id)
                if name == "documents" else (organization_id,)
            )
            result[name] = [
                {key: row[key] for key in row.keys()}
                for row in conn.execute(sql, params).fetchall()
            ]
    seen: set[int] = set()
    latest = []
    for event in result["events"]:
        if event["asset_id"] in seen:
            continue
        seen.add(event["asset_id"])
        details = json.loads(event["details"]) if event.get("details") else None
        event["details"] = details if isinstance(details, dict) else {}
        latest.append(event)
    result["events"] = latest
    return result
