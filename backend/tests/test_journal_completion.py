from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.fleet.journal.control_room.completion_service import journal_completion


client = TestClient(app)
CONTROL = "/api/fleet/journal-control-room"


def seed_completion_dataset() -> str:
    day = client.get(CONTROL).json()["context"]["operational_date"]
    timestamp = f"{day}T10:00:00+00:00"
    with db_session() as conn:
        planning_import = conn.execute(
            "INSERT INTO imports (dataset_type,original_filename,imported_at,column_mapping,normalized_rows) VALUES ('planning','completion.csv',?,'{}','[]')",
            (timestamp,),
        ).lastrowid
        fleet_import = conn.execute(
            "INSERT INTO imports (dataset_type,original_filename,imported_at,column_mapping,normalized_rows) VALUES ('fleet','fleet.csv',?,'{}','[]')",
            (timestamp,),
        ).lastrowid
        planning_id = conn.execute(
            """INSERT INTO plannings (
                operation_date,station,source_planning_import_id,source_fleet_import_id,
                status,version,reserve_threshold,configuration,summary,conflicts,
                generation_metadata,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (day, "QA", planning_import, fleet_import, "ready", 1, 1, "{}", "{}", "[]", "{}", timestamp, timestamp),
        ).lastrowid
        for index in range(1, 79):
            plate = f"QA{index:05d}"
            asset_id = conn.execute(
                """INSERT INTO fleet_assets (
                    external_identifier,plate,category,status,availability,notes,
                    capabilities,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (f"COMP-{index:03d}", plate, "Furgone", "active", "available", None, "[]", timestamp, timestamp),
            ).lastrowid
            conn.execute(
                """INSERT INTO assignments (
                    planning_id,operation_date,station,route_id,cycle_or_wave,
                    driver_id,driver_name,vehicle_id,plate,assignment_status,
                    assignment_source,confidence,reasons,data_used,warnings,
                    alternatives,manual_override,confirmed,notes,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (planning_id, day, "QA", f"ROUTE-{index:03d}", None,
                 f"DRV-{index:03d}", f"Driver {index:03d}", f"COMP-{index:03d}", plate,
                 "confirmed", "manual", 1.0, "[]", "[]", "[]", "[]", 0, 1, None, timestamp, timestamp),
            )
            for operation_type, completed_limit in (("check_out", 76), ("check_in", 72)):
                if index > completed_limit:
                    continue
                session_id = str(uuid4())
                movement_id = str(uuid4())
                conn.execute(
                    """INSERT INTO journal_sessions (
                        id,token_hash,operation_type,asset_id,plate_snapshot,
                        declared_driver_identifier,status,created_at,expires_at,
                        completed_at,organization_id,source,lifecycle_status,
                        operational_date,warnings_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (session_id, "qa", operation_type, asset_id, plate,
                     f"DRV-{index:03d}", "completed", timestamp, timestamp,
                    timestamp, "test-organization", "driver", "completed", day, "[]"),
                )
                anomaly = operation_type == "check_in" and index <= 3
                conn.execute(
                    """INSERT INTO asset_movements (
                        id,session_id,schema_version,organization_id,operational_unit_id,
                        asset_id,plate_snapshot,declared_driver_identifier,operation_type,
                        occurred_at,timezone,odometer_km,fuel_percentage,anomaly_present,
                        anomaly_description,client_submission_id,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (movement_id, session_id, "1.0", "test-organization", "QA", asset_id,
                     plate, f"DRV-{index:03d}", operation_type, timestamp,
                     "Europe/Rome", 42000 + index, 50, int(anomaly),
                     "Anomalia QA" if anomaly else None, f"qa-{movement_id}", timestamp),
                )
    return day


def test_completion_uses_planning_as_source_of_truth_and_filters_real_gaps():
    day = seed_completion_dataset()
    payload = client.get(CONTROL).json()
    completion = payload["completion"]
    assert completion["operational_date"] == day
    assert completion["drivers_expected"] == 78
    assert completion["check_out"] == {"expected": 78, "completed": 76, "missing": 2}
    assert completion["check_in"] == {"expected": 78, "completed": 72, "missing": 6}
    assert completion["procedures"]["anomalies"] == 3
    assert len(completion["missing"]) == 8
    assert completion["missing"][0]["operation_type"] == "check_in"
    assert all(item["planning_id"] == completion["planning_id"] for item in completion["missing"])
    assert any(card["title"] == "Mancano 6 rientri" for card in completion["decisions"])
    assert any(card["title"] == "Mancano 2 prese in carico" for card in completion["decisions"])

    checkout_missing = client.get(CONTROL, params={"completion_filter": "checkout_missing"}).json()
    assert checkout_missing["items"] == []
    assert len(checkout_missing["completion"]["missing"]) == 2
    checkin_completed = client.get(CONTROL, params={"completion_filter": "checkin_completed"}).json()
    assert len(checkin_completed["items"]) == 72
    assert checkin_completed["completion"]["missing"] == []
    anomalies = client.get(CONTROL, params={"completion_filter": "procedures_anomaly"}).json()
    assert len(anomalies["items"]) == 3

    controlled = journal_completion(
        payload["context"], payload["items"],
        now=datetime.fromisoformat(f"{day}T12:00:00+00:00").astimezone(timezone.utc),
    )
    assert controlled["procedures"]["late"] == 2


def test_invalidated_and_cancelled_assignments_are_exceptions_not_false_positives():
    day = seed_completion_dataset()
    with db_session() as conn:
        planning_id = conn.execute(
            "SELECT id FROM plannings WHERE operation_date=? ORDER BY id DESC LIMIT 1", (day,),
        ).fetchone()["id"]
        conn.execute("UPDATE assignments SET assignment_status='invalidated' WHERE planning_id=? AND route_id='ROUTE-078'", (planning_id,))
        conn.execute(
            """INSERT INTO planning_events (
                planning_id,event_type,entity_type,entity_id,reason,simulated,applied,
                impact_summary,payload,diff,actor,created_at,applied_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (planning_id, "route_aborted", "route", "ROUTE-077", "QA", 0, 1,
             "Rotta annullata", "{}", "{}", "qa", f"{day}T10:00:00+00:00", f"{day}T10:00:00+00:00"),
        )
    completion = client.get(CONTROL).json()["completion"]
    assert completion["drivers_expected"] == 76
    assert len(completion["exceptions"]) == 2
    assert {item["route_id"] for item in completion["exceptions"]} == {"ROUTE-077", "ROUTE-078"}
