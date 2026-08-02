from app.core.database import db_session


def list_sources(vehicle_id: int | None = None) -> list[dict]:
    restriction = " AND a.id = ?" if vehicle_id else ""
    params = (vehicle_id,) if vehicle_id else ()
    queries = [
        f"""SELECT 'document' AS source_module, d.id AS source_id, a.id AS vehicle_id,
                   a.plate, a.external_identifier, a.category AS vehicle_model,
                   d.document_type AS deadline_type, d.title, d.expires_at AS due_date,
                   d.issuer AS company
            FROM fleet_vehicle_documents d JOIN fleet_assets a ON a.id=d.vehicle_id
            WHERE d.expires_at IS NOT NULL AND d.expires_at <> ''{restriction}""",
        f"""SELECT 'insurance' AS source_module, p.id AS source_id, a.id AS vehicle_id,
                   a.plate, a.external_identifier, a.category AS vehicle_model,
                   'assicurazione' AS deadline_type, p.coverage_type AS title,
                   p.expires_on AS due_date, p.company
            FROM fleet_insurance_policies p JOIN fleet_assets a ON a.id=p.vehicle_id
            WHERE p.expires_on IS NOT NULL AND p.expires_on <> ''{restriction}""",
        f"""SELECT 'contract' AS source_module, p.asset_id AS source_id, a.id AS vehicle_id,
                   a.plate, a.external_identifier, a.category AS vehicle_model,
                   'contratto' AS deadline_type, p.contract_type AS title,
                   p.expires_on AS due_date, COALESCE(p.company,p.owner_company) AS company
            FROM fleet_asset_profiles p JOIN fleet_assets a ON a.id=p.asset_id
            WHERE p.expires_on IS NOT NULL AND p.expires_on <> ''{restriction}""",
        f"""SELECT 'maintenance' AS source_module, m.id AS source_id, a.id AS vehicle_id,
                   a.plate, a.external_identifier, a.category AS vehicle_model,
                   'manutenzione_programmata' AS deadline_type, m.description AS title,
                   m.expected_at AS due_date, m.repair_shop AS company
            FROM fleet_maintenances m JOIN fleet_assets a ON a.id=m.vehicle_id
            WHERE m.expected_at IS NOT NULL AND m.expected_at <> ''
              AND m.status NOT IN ('completata','annullata'){restriction}""",
        f"""SELECT 'rental' AS source_module, r.id AS source_id, a.id AS vehicle_id,
                   a.plate, a.external_identifier, a.category AS vehicle_model,
                   'noleggio' AS deadline_type, r.replacement_vehicle AS title,
                   r.expected_end_date AS due_date, r.rental_company AS company
            FROM fleet_rentals r JOIN fleet_assets a ON a.id=r.vehicle_id
            WHERE r.expected_end_date IS NOT NULL AND r.expected_end_date <> ''
              AND r.status NOT IN ('concluso','annullato'){restriction}""",
    ]
    items: list[dict] = []
    with db_session() as conn:
        for query in queries:
            rows = conn.execute(query, params).fetchall()
            items.extend({key: row[key] for key in row.keys()} for row in rows)
    return items
