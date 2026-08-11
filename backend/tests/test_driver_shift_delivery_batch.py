import csv
import io
from time import perf_counter

from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_distribution_service as service
from app.plugins.workforce.application.driver_shift_delivery_provider import MANUAL_SHARE_PROVIDER
from app.plugins.workforce.domain.driver_shift_contact import contact_readiness
from tests.test_driver_shift_distribution import BASE, ORG, _member, _planning, _scenario, _shift, _token


def _contact(member_id: int, *, phone: str | None = None, email: str | None = None,
             organization_id: str = ORG) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE workforce_members SET phone=?, email=? WHERE id=? AND organization_id=?",
            (phone, email, member_id, organization_id),
        )


def _prepared_scenario() -> tuple[TestClient, dict, list[int]]:
    planning_id, members = _scenario()
    _contact(members[0], phone="333 123 4567")
    _contact(members[1], email=" DRIVER.TWO@Example.Test ")
    _contact(members[2], phone="invalid")
    client = TestClient(app)
    model = client.post(f"{BASE}/driver-shift-plannings/{planning_id}/distribution").json()
    return client, model, members


def test_contact_readiness_normalizes_phone_and_email_without_mutating_source():
    phone = contact_readiness("333 123 4567", None)
    email = contact_readiness(None, " DRIVER@Example.Test ")
    assert phone.phone == "+393331234567" and phone.readiness == "READY"
    assert email.email == "driver@example.test" and email.readiness == "READY"
    assert phone.available_channels == ("PHONE",)
    assert email.available_channels == ("EMAIL",)


def test_missing_and_invalid_contact_are_distinct_and_summary_is_automatic():
    client, model, members = _prepared_scenario()
    _contact(members[2])
    refreshed = client.get(
        f"{BASE}/driver-shift-plannings/{model['distribution']['driver_shift_planning_id']}/distribution"
    ).json()
    assert refreshed["summary"]["contact_ready"] == 2
    assert refreshed["summary"]["missing_contact"] == 1
    _contact(members[2], phone="not-a-phone")
    refreshed = client.get(
        f"{BASE}/driver-shift-plannings/{model['distribution']['driver_shift_planning_id']}/distribution"
    ).json()
    assert refreshed["summary"]["invalid_contact"] == 1
    assert {item["readiness"] for item in refreshed["recipients"]} == {"READY", "INVALID_CONTACT"}


def test_prepare_without_ids_selects_all_ready_and_excludes_invalid():
    client, model, _ = _prepared_scenario()
    response = client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/prepare-batch",
        json={"recipient_ids": None},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requested_count"] == 3
    assert body["prepared_count"] == 2
    assert len(body["excluded_recipient_ids"]) == 1
    assert body["delivery_channel"] == "MANUAL_SHARE"


def test_prepare_subset_reuses_personal_url_and_never_marks_sent():
    client, model, _ = _prepared_scenario()
    ready = [item for item in model["recipients"] if item["display_name"] == "Mario Rossi"][0]
    first = client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/prepare-batch",
        json={"recipient_ids": [ready["id"]]},
    ).json()
    second = client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/prepare-batch",
        json={"recipient_ids": [ready["id"]]},
    ).json()
    assert first["prepared_count"] == 1
    assert first["recipients"][0]["personal_url"] == second["recipients"][0]["personal_url"]
    refreshed = client.get(
        f"{BASE}/driver-shift-plannings/{model['distribution']['driver_shift_planning_id']}/distribution"
    ).json()
    assert {item["delivery_status"] for item in refreshed["recipients"]} == {"READY"}
    assert refreshed["distribution"]["status"] == "READY"


def test_cross_organization_recipient_is_rejected():
    client, model, _ = _prepared_scenario()
    other_member = _member("OTHER-BATCH", "Other Driver", "other-organization")
    _contact(other_member, phone="+393331112233", organization_id="other-organization")
    other_planning = _planning(organization_id="other-organization", label="Other batch")
    _shift(other_planning, other_member, "2026-08-17", organization_id="other-organization")
    other_model = service.prepare_distribution("other-organization", other_planning, "other@test")
    other_recipient = other_model.recipients[0].id
    response = client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/prepare-batch",
        json={"recipient_ids": [other_recipient]},
    )
    assert response.status_code == 404


def test_csv_contains_only_safe_batch_fields_and_no_internal_identity():
    client, model, _ = _prepared_scenario()
    response = client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/export.csv",
        json={"recipient_ids": None},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    assert response.headers["content-disposition"] == 'attachment; filename="turni-2026-08-17_2026-08-23.csv"'
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2
    assert set(rows[0]) == {
        "driver", "phone", "email", "personal_url", "message", "period_start", "period_end",
    }
    serialized = response.text.casefold()
    for forbidden in ("workforce_member_id", "transporter", "contract", "quality", "provenance"):
        assert forbidden not in serialized


def test_message_template_uses_first_name_period_and_personal_url():
    client, model, _ = _prepared_scenario()
    body = client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/prepare-batch",
        json={"recipient_ids": None},
    ).json()
    message = body["recipients"][0]["message"]
    assert message.startswith("Ciao Mario,") or message.startswith("Ciao Yassine,")
    assert "2026-08-17" in message and "2026-08-23" in message
    assert body["recipients"][0]["personal_url"] in message


def test_acknowledgement_summary_is_unchanged_by_batch_preparation():
    client, model, _ = _prepared_scenario()
    token = _token(client, model, 0)
    public = TestClient(app, headers={"X-Test-Auth-Harness": ""})
    public.get(f"/api/public/driver-shifts/{token}")
    public.post(f"/api/public/driver-shifts/{token}/acknowledge")
    before = client.get(
        f"{BASE}/driver-shift-plannings/{model['distribution']['driver_shift_planning_id']}/distribution"
    ).json()["summary"]
    client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/prepare-batch",
        json={"recipient_ids": None},
    )
    after = client.get(
        f"{BASE}/driver-shift-plannings/{model['distribution']['driver_shift_planning_id']}/distribution"
    ).json()["summary"]
    assert before["opened"] == after["opened"] == 1
    assert before["acknowledged"] == after["acknowledged"] == 1


def test_superseded_distribution_cannot_prepare_batch_and_no_fake_provider_exists():
    client, model, members = _prepared_scenario()
    with db_session() as conn:
        conn.execute("UPDATE driver_shift_plannings SET status='SUPERSEDED' WHERE id=?", (
            model["distribution"]["driver_shift_planning_id"],
        ))
    revision = _planning(version=2, label="Batch revision 2")
    _shift(revision, members[0], "2026-08-19", version=2)
    client.post(f"{BASE}/driver-shift-plannings/{revision}/distribution")
    response = client.post(
        f"{BASE}/driver-shift-distributions/{model['distribution']['id']}/prepare-batch",
        json={"recipient_ids": None},
    )
    assert response.status_code == 422
    assert MANUAL_SHARE_PROVIDER.can_send("MANUAL_SHARE") is False
    try:
        MANUAL_SHARE_PROVIDER.send(recipient={}, message="x", url="x")
    except NotImplementedError:
        pass
    else:
        raise AssertionError("Il provider manuale non deve simulare invii.")


def test_prepare_300_ready_recipients_is_batch_and_under_two_seconds():
    planning_id = _planning()
    with db_session() as conn:
        rows = [(f"BATCH-{index}", f"Batch Driver {index}", f"+39333{index:07d}", ORG)
                for index in range(300)]
        conn.executemany(
            """INSERT INTO workforce_members (
                   external_identifier, display_name, capabilities, active,
                   source_reference, created_at, updated_at, phone, organization_id
               ) VALUES (?, ?, '[]', 1, 'batch-performance',
                         '2026-08-11T09:00:00Z', '2026-08-11T09:00:00Z', ?, ?)""",
            rows,
        )
        members = conn.execute(
            "SELECT id FROM workforce_members WHERE organization_id=? ORDER BY id", (ORG,),
        ).fetchall()
        conn.executemany(
            """INSERT INTO driver_shift_planning_published_rows (
                   organization_id, driver_shift_planning_id, planning_version,
                   workforce_member_id, operational_date, status_code, availability,
                   shift_code, station, provenance_summary, published_at
               ) VALUES (?, ?, 1, ?, '2026-08-17', 'scheduled', 1, 'A', 'DLO2', '[]',
                         '2026-08-11T09:00:00Z')""",
            [(ORG, planning_id, row["id"]) for row in members],
        )
    distribution = service.prepare_distribution(ORG, planning_id, "performance@test")
    started = perf_counter()
    batch = service.prepare_batch(ORG, distribution.distribution.id)
    elapsed = perf_counter() - started
    assert batch.prepared_count == 300
    assert elapsed < 2
