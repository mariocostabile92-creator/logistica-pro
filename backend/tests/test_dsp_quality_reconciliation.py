from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.domain import Role
from app.auth.password_service import hash_password
from app.auth.repository import create_user
from app.core.database import db_session
from app.main import app
from app.plugins.dsp_quality.application.drivers_read_service import get_latest_drivers
from app.plugins.dsp_quality.application.import_contract import QualityImportDocument
from app.plugins.dsp_quality.application.import_service import ingest_quality_document
from app.plugins.dsp_quality.application.mapping_service import MappingConflictError
from app.plugins.dsp_quality.application.reconciliation_service import (
    ReconciliationNotFoundError,
    delete_mapping,
    mapping_history,
    put_mapping,
    reconciliation_state,
    search_workforce_candidates,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dsp_quality_week47.json"
FIRST_TRANSPORTER = "A10GSCDE4XETEE"
SECOND_TRANSPORTER = "A1220Y3BKPI76Z"


def quality_document(week: int = 45) -> QualityImportDocument:
    base = QualityImportDocument.model_validate_json(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )
    return base.model_copy(update={
        "identity": base.identity.model_copy(update={"reported_week": week}),
        "revision": base.revision.model_copy(update={
            "source_filename": f"Week-{week}.pdf",
            "raw_period_label": f"Week {week} - 2025",
        }),
    })


def persist(organization_id: str, week: int = 45):
    return ingest_quality_document(
        organization_id=organization_id,
        document=quality_document(week),
        source_content=f"quality-{organization_id}-{week}".encode(),
        imported_by="quality-test",
    )


def create_member(
    organization_id: str,
    display_name: str,
    external_identifier: str,
    station: str = "DLO2",
) -> int:
    with db_session() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workforce_members (
                external_identifier, display_name, station, employment_type,
                capabilities, active, source_reference, created_at, updated_at,
                organization_id
            ) VALUES (?, ?, ?, 'full_time', '[]', 1, 'q8-test', ?, ?, ?)
            """,
            (
                external_identifier,
                display_name,
                station,
                "2026-08-09T10:00:00+00:00",
                "2026-08-09T10:00:00+00:00",
                organization_id,
            ),
        )
        return int(cursor.lastrowid)


def test_reconciliation_list_and_real_summary_are_read_only():
    persist("q8-org")
    with db_session() as conn:
        before = conn.execute(
            "SELECT COUNT(*) count FROM workforce_external_identity_events"
        ).fetchone()["count"]

    result = reconciliation_state("q8-org")

    assert result.available is True
    assert result.week == 45
    assert result.summary.model_dump() == {
        "total": 5, "matched": 0, "unmapped": 5, "ambiguous": 0,
    }
    assert result.rows[0].transporter_external_id == FIRST_TRANSPORTER
    assert result.rows[0].delivered == "135"
    with db_session() as conn:
        after = conn.execute(
            "SELECT COUNT(*) count FROM workforce_external_identity_events"
        ).fetchone()["count"]
    assert after == before


def test_create_mapping_is_exact_audited_and_updates_q7_immediately():
    persist("q8-org")
    member_id = create_member("q8-org", "Mario Rossi", "WF-MARIO")

    mapped = put_mapping(
        organization_id="q8-org",
        external_id=FIRST_TRANSPORTER,
        workforce_member_id=member_id,
        actor="admin-q8",
        expected_updated_at=None,
    )

    assert mapped.mapping_status == "MATCHED"
    assert mapped.workforce_display_name == "Mario Rossi"
    current = next(
        row for row in get_latest_drivers("q8-org").rows
        if row.transporter_external_id == FIRST_TRANSPORTER
    )
    assert current.workforce_member_id == member_id
    assert current.workforce_display_name == "Mario Rossi"
    event = mapping_history("q8-org", FIRST_TRANSPORTER).items[0]
    assert event.action == "mapping_created"
    assert event.previous_workforce_member_id is None
    assert event.new_workforce_member_id == member_id
    assert event.actor == "admin-q8"


def test_replace_and_remove_preserve_structured_history():
    persist("q8-org")
    first_id = create_member("q8-org", "Mario Rossi", "WF-MARIO")
    second_id = create_member("q8-org", "Giulia Bianchi", "WF-GIULIA")
    created = put_mapping(
        organization_id="q8-org", external_id=FIRST_TRANSPORTER,
        workforce_member_id=first_id, actor="creator", expected_updated_at=None,
    )
    replaced = put_mapping(
        organization_id="q8-org", external_id=FIRST_TRANSPORTER,
        workforce_member_id=second_id, actor="replacer",
        expected_updated_at=created.updated_at.isoformat(),
    )
    removed = delete_mapping(
        organization_id="q8-org", external_id=FIRST_TRANSPORTER,
        actor="remover", expected_updated_at=replaced.updated_at.isoformat(),
    )

    assert removed.mapping_status == "UNMAPPED"
    history = mapping_history("q8-org", FIRST_TRANSPORTER).items
    assert [item.action for item in history] == [
        "mapping_removed", "mapping_replaced", "mapping_created",
    ]
    assert history[0].previous_workforce_display_name == "Giulia Bianchi"
    assert history[1].previous_workforce_display_name == "Mario Rossi"
    assert history[1].new_workforce_display_name == "Giulia Bianchi"


def test_stale_mapping_update_returns_conflict_without_overwrite():
    persist("q8-org")
    first_id = create_member("q8-org", "Mario Rossi", "WF-MARIO")
    second_id = create_member("q8-org", "Giulia Bianchi", "WF-GIULIA")
    created = put_mapping(
        organization_id="q8-org", external_id=FIRST_TRANSPORTER,
        workforce_member_id=first_id, actor="creator", expected_updated_at=None,
    )
    put_mapping(
        organization_id="q8-org", external_id=FIRST_TRANSPORTER,
        workforce_member_id=second_id, actor="replacer",
        expected_updated_at=created.updated_at.isoformat(),
    )

    with pytest.raises(MappingConflictError):
        delete_mapping(
            organization_id="q8-org", external_id=FIRST_TRANSPORTER,
            actor="stale", expected_updated_at=created.updated_at.isoformat(),
        )
    assert reconciliation_state("q8-org").rows[0].workforce_member_id == second_id


def test_mapping_persists_across_weeks_without_mutating_history():
    persist("q8-org", week=45)
    member_id = create_member("q8-org", "Mario Rossi", "WF-MARIO")
    put_mapping(
        organization_id="q8-org", external_id=FIRST_TRANSPORTER,
        workforce_member_id=member_id, actor="admin", expected_updated_at=None,
    )
    persist("q8-org", week=46)

    current = next(
        row for row in get_latest_drivers("q8-org").rows
        if row.transporter_external_id == FIRST_TRANSPORTER
    )
    with db_session() as conn:
        historical = conn.execute(
            """
            SELECT mapping_status, workforce_member_id
            FROM dsp_quality_transporter_rows
            WHERE transporter_external_id = ? ORDER BY rowid
            """,
            (FIRST_TRANSPORTER,),
        ).fetchall()
    assert current.mapping_status == "MATCHED"
    assert current.workforce_member_id == member_id
    assert len(historical) == 2
    assert historical[0]["mapping_status"] == "UNMAPPED"
    assert historical[1]["mapping_status"] == "MATCHED"


def test_organization_isolation_for_transporter_workforce_mapping_and_audit():
    persist("q8-org-a")
    persist("q8-org-b")
    member_b = create_member("q8-org-b", "Driver Segreto B", "WF-B")

    with pytest.raises(ValueError, match="Workforce member non trovato"):
        put_mapping(
            organization_id="q8-org-a", external_id=FIRST_TRANSPORTER,
            workforce_member_id=member_b, actor="admin-a", expected_updated_at=None,
        )
    mapped_b = put_mapping(
        organization_id="q8-org-b", external_id=FIRST_TRANSPORTER,
        workforce_member_id=member_b, actor="admin-b", expected_updated_at=None,
    )
    assert reconciliation_state("q8-org-a").summary.matched == 0
    assert reconciliation_state("q8-org-b").summary.matched == 1
    assert mapping_history("q8-org-a", FIRST_TRANSPORTER).items == []
    assert mapped_b.workforce_member_id == member_b


def test_unknown_or_other_tenant_transporter_is_rejected_exactly():
    persist("q8-org-a")
    member_id = create_member("q8-org-a", "Mario Rossi", "WF-MARIO")

    with pytest.raises(ReconciliationNotFoundError):
        put_mapping(
            organization_id="q8-org-a", external_id="A10GSCDE4XETE",
            workforce_member_id=member_id, actor="admin", expected_updated_at=None,
        )
    with pytest.raises(ReconciliationNotFoundError):
        put_mapping(
            organization_id="q8-org-b", external_id=FIRST_TRANSPORTER,
            workforce_member_id=member_id, actor="admin", expected_updated_at=None,
        )


def test_workforce_candidates_are_minimal_exactly_tenant_scoped_and_do_not_map():
    persist("q8-org-a")
    member_a = create_member("q8-org-a", "Mario Rossi", "WF-MARIO")
    create_member("q8-org-b", "Mario Segreto", "WF-SEGRETO")
    with db_session() as conn:
        before_members = conn.execute(
            "SELECT COUNT(*) count FROM workforce_members"
        ).fetchone()["count"]

    result = search_workforce_candidates("q8-org-a", "Mario")

    assert [item.workforce_member_id for item in result.items] == [member_a]
    assert result.items[0].station == "DLO2"
    assert result.items[0].contract == "full_time"
    assert reconciliation_state("q8-org-a").summary.matched == 0
    with db_session() as conn:
        after_members = conn.execute(
            "SELECT COUNT(*) count FROM workforce_members"
        ).fetchone()["count"]
    assert after_members == before_members


def test_inverse_uniqueness_is_not_imposed_for_historical_external_ids():
    persist("q8-org")
    member_id = create_member("q8-org", "Mario Rossi", "WF-MARIO")
    put_mapping(
        organization_id="q8-org", external_id=FIRST_TRANSPORTER,
        workforce_member_id=member_id, actor="admin", expected_updated_at=None,
    )
    put_mapping(
        organization_id="q8-org", external_id=SECOND_TRANSPORTER,
        workforce_member_id=member_id, actor="admin", expected_updated_at=None,
    )
    assert reconciliation_state("q8-org").summary.matched == 2


def test_reconciliation_api_mutations_and_conflict_use_authenticated_org():
    persist("test-organization")
    member_id = create_member("test-organization", "Mario Rossi", "WF-MARIO")
    client = TestClient(app)

    read = client.get("/api/dsp-quality/transporter-mappings/reconciliation")
    candidates = client.get(
        "/api/dsp-quality/transporter-mappings/workforce-candidates",
        params={"q": "Mario"},
    )
    created = client.put(
        f"/api/dsp-quality/transporter-mappings/{FIRST_TRANSPORTER}",
        json={"workforce_member_id": member_id, "expected_updated_at": None},
    )
    stale = client.put(
        f"/api/dsp-quality/transporter-mappings/{FIRST_TRANSPORTER}",
        json={"workforce_member_id": member_id, "expected_updated_at": None},
    )

    assert read.status_code == 200
    assert candidates.status_code == 200
    assert candidates.json()["items"][0]["display_name"] == "Mario Rossi"
    assert created.status_code == 200
    assert stale.status_code == 409
    history = client.get(
        f"/api/dsp-quality/transporter-mappings/{FIRST_TRANSPORTER}/history"
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["action"] == "mapping_created"


def test_viewer_can_read_but_cannot_modify_mapping():
    client = TestClient(app, headers={"X-Auth-Enforce": "1"})
    password = "Password-sicura-123"
    create_user(
        "quality-q8-viewer@example.test",
        hash_password(password),
        Role.VIEWER,
        "Quality Q8 Viewer",
    )
    assert client.post(
        "/api/auth/login",
        json={"email": "quality-q8-viewer@example.test", "password": password},
    ).status_code == 200

    assert client.get(
        "/api/dsp-quality/transporter-mappings/reconciliation"
    ).status_code == 200
    assert client.put(
        f"/api/dsp-quality/transporter-mappings/{FIRST_TRANSPORTER}",
        json={"workforce_member_id": 1, "expected_updated_at": None},
    ).status_code == 403
