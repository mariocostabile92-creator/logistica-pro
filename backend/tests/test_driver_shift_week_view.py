from fastapi.testclient import TestClient

from app.core.database import db_session
from app.main import app
from app.plugins.workforce.application import driver_shift_driver_session_service
from tests.test_driver_shift_distribution import BASE, ORG, _member, _planning, _scenario


PUBLIC_HEADERS = {"X-Test-Auth-Harness": ""}


def _public() -> TestClient:
    return TestClient(app, headers=PUBLIC_HEADERS)


def _add_shift(
    planning_id: int,
    member_id: int,
    operational_date: str,
    code: str,
    *,
    status: str = "scheduled",
    available: bool = True,
    station: str = "DLO2",
    start_time: str | None = "08:00",
    end_time: str | None = "17:00",
    version: int = 1,
) -> None:
    with db_session() as conn:
        conn.execute(
            """INSERT INTO driver_shift_planning_published_rows (
                   organization_id, driver_shift_planning_id, planning_version,
                   workforce_member_id, operational_date, status_code, availability,
                   shift_code, start_time, end_time, station, transporter_id,
                   provenance_summary, published_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]',
                         '2026-08-11T09:00:00Z')""",
            (
                ORG, planning_id, version, member_id, operational_date, status,
                int(available), code, start_time, end_time, station,
                f"PRIVATE-T-{member_id}",
            ),
        )


def _weekly_setup():
    planning_id, members = _scenario(2)
    with db_session() as conn:
        conn.execute(
            "DELETE FROM driver_shift_planning_published_rows WHERE driver_shift_planning_id=?",
            (planning_id,),
        )
    mario_codes = [
        ("2026-08-17", "C1", "scheduled", True, "08:15", "17:00"),
        ("2026-08-18", "R", "rest", False, None, None),
        ("2026-08-19", "FERIE", "holiday", False, None, None),
        ("2026-08-20", "PERMESSO", "leave", False, None, None),
        ("2026-08-21", "C2", "scheduled", True, "09:00", "18:00"),
        ("2026-08-22", "NOTTE-X", "scheduled", True, "22:00", "06:00"),
        ("2026-08-23", "C1", "scheduled", True, "08:15", "17:00"),
    ]
    for day, code, status, available, start, end in mario_codes:
        _add_shift(
            planning_id, members[0], day, code, status=status,
            available=available, start_time=start, end_time=end,
        )
    _add_shift(planning_id, members[1], "2026-08-17", "Y1", station="DLO3")
    _add_shift(planning_id, members[1], "2026-08-18", "R", status="rest", available=False,
               start_time=None, end_time=None, station="DLO3")

    admin = TestClient(app)
    distribution = admin.post(
        f"{BASE}/driver-shift-plannings/{planning_id}/distribution"
    ).json()
    distribution_id = distribution["distribution"]["id"]
    credentials = admin.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/credentials/prepare"
    ).json()["initial_credentials"]
    portal = admin.post(
        f"{BASE}/driver-shift-distributions/{distribution_id}/portal"
    ).json()
    token = portal["access_url"].split("#token=", 1)[1]
    credentials_by_name = {item["display_name"]: item for item in credentials}
    return admin, planning_id, members, distribution, credentials_by_name, token


def _login(client: TestClient, token: str, credential: dict):
    return client.post(
        "/api/public/driver-shifts/portal/login",
        json={
            "portal_token": token,
            "access_code": credential["access_code"],
            "pin": credential["initial_pin"],
            "remember_device": False,
        },
    )


def test_week_is_session_scoped_chronological_safe_and_tracks_opening():
    admin, planning_id, _, _, credentials, token = _weekly_setup()
    mario = _public()
    assert _login(mario, token, credentials["Mario Rossi"]).status_code == 200

    response = mario.get("/api/public/driver-shifts/me/shifts")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private, max-age=0"
    body = response.json()
    assert body["driver_name"] == "Mario Rossi"
    assert body["period_start"] == "2026-08-17"
    assert body["period_end"] == "2026-08-23"
    assert [day["operational_date"] for day in body["days"]] == [
        f"2026-08-{day:02d}" for day in range(17, 24)
    ]
    assert body["days"][0]["date_label"] == "Lunedì 17 agosto"
    serialized = response.text.casefold()
    for forbidden in (
        "organization_id", "workforce_member_id", "distribution_id",
        "transporter_id", "provenance", "contract", "quality", "private-t-",
    ):
        assert forbidden not in serialized

    tracked = admin.get(
        f"{BASE}/driver-shift-plannings/{planning_id}/distribution"
    ).json()
    mario_recipient = next(
        item for item in tracked["recipients"] if item["display_name"] == "Mario Rossi"
    )
    assert mario_recipient["access_status"] == "OPENED"


def test_week_preserves_codes_semantics_times_station_and_unknown_values():
    _, _, _, _, credentials, token = _weekly_setup()
    mario = _public()
    _login(mario, token, credentials["Mario Rossi"])
    days = mario.get("/api/public/driver-shifts/me/shifts").json()["days"]
    shifts = [day["shifts"][0] for day in days]

    assert shifts[0] == {
        "raw_shift_code": "C1", "display_label": "C1",
        "start_time": "08:15", "end_time": "17:00",
        "status": "scheduled", "availability": True, "station": "DLO2",
    }
    assert shifts[1]["raw_shift_code"] == "R" and shifts[1]["display_label"] == "Riposo"
    assert shifts[2]["display_label"] == "Ferie"
    assert shifts[3]["display_label"] == "Permesso"
    assert shifts[5]["raw_shift_code"] == shifts[5]["display_label"] == "NOTTE-X"


def test_driver_sessions_never_cross_expose_shift_rows():
    _, _, _, _, credentials, token = _weekly_setup()
    mario, yassine = _public(), _public()
    _login(mario, token, credentials["Mario Rossi"])
    _login(yassine, token, credentials["Yassine Zyadi"])

    mario_body = mario.get("/api/public/driver-shifts/me/shifts").json()
    yassine_body = yassine.get("/api/public/driver-shifts/me/shifts").json()
    assert mario_body["driver_name"] == "Mario Rossi"
    assert yassine_body["driver_name"] == "Yassine Zyadi"
    assert mario_body["days"][0]["shifts"][0]["raw_shift_code"] == "C1"
    assert yassine_body["days"][0]["shifts"][0]["raw_shift_code"] == "Y1"
    assert "NOTTE-X" not in str(yassine_body)


def test_missing_period_day_is_explicitly_unavailable_and_never_rest():
    _, planning_id, members, _, credentials, token = _weekly_setup()
    with db_session() as conn:
        conn.execute(
            """DELETE FROM driver_shift_planning_published_rows
               WHERE driver_shift_planning_id=? AND workforce_member_id=?
                 AND operational_date='2026-08-23'""",
            (planning_id, members[0]),
        )
    mario = _public()
    _login(mario, token, credentials["Mario Rossi"])
    sunday = mario.get("/api/public/driver-shifts/me/shifts").json()["days"][-1]
    assert sunday["missing"] is True
    assert sunday["shifts"] == [{
        "raw_shift_code": None,
        "display_label": "Turno non disponibile",
        "start_time": None,
        "end_time": None,
        "status": None,
        "availability": None,
        "station": None,
    }]


def test_projection_preserves_multiple_rows_per_day_and_periods_longer_than_week():
    rows = [
        {"operational_date": "2026-08-17", "shift_code": "C1", "status_code": "scheduled",
         "availability": 1, "start_time": "08:00", "end_time": "12:00", "station": "DLO2"},
        {"operational_date": "2026-08-17", "shift_code": "C2", "status_code": "scheduled",
         "availability": 1, "start_time": "14:00", "end_time": "18:00", "station": "DLO2"},
    ]
    days = driver_shift_driver_session_service.build_week_days(
        "2026-08-17", "2026-08-25", rows,
    )
    assert len(days) == 9
    assert [shift.raw_shift_code for shift in days[0].shifts] == ["C1", "C2"]
    assert all(day.date_label for day in days)


def test_acknowledgement_is_idempotent_and_visible_in_admin_tracking():
    admin, planning_id, _, _, credentials, token = _weekly_setup()
    mario = _public()
    _login(mario, token, credentials["Mario Rossi"])
    before = mario.get("/api/public/driver-shifts/me/shifts").json()
    assert before["acknowledged"] is False and before["acknowledged_at"] is None

    first = mario.post("/api/public/driver-shifts/me/acknowledge")
    second = mario.post("/api/public/driver-shifts/me/acknowledge")
    assert first.status_code == second.status_code == 200
    assert first.json()["acknowledged_at"] == second.json()["acknowledged_at"]
    assert second.json()["acknowledged"] is True

    tracked = admin.get(
        f"{BASE}/driver-shift-plannings/{planning_id}/distribution"
    ).json()
    by_name = {item["display_name"]: item for item in tracked["recipients"]}
    assert by_name["Mario Rossi"]["access_status"] == "ACKNOWLEDGED"
    assert by_name["Mario Rossi"]["acknowledged_at"] is not None
    assert by_name["Yassine Zyadi"]["access_status"] == "NOT_OPENED"
    assert tracked["summary"]["acknowledged"] == 1


def test_session_revocation_and_distribution_supersede_block_week_and_ack():
    admin, _, members, distribution, credentials, token = _weekly_setup()
    mario = _public()
    _login(mario, token, credentials["Mario Rossi"])
    assert admin.post(f"{BASE}/credentials/{members[0]}/revoke").status_code == 200
    assert mario.get("/api/public/driver-shifts/me/shifts").status_code == 401
    assert mario.post("/api/public/driver-shifts/me/acknowledge").status_code == 401

    other = _public()
    credentials["Yassine Zyadi"]["initial_pin"] = credentials["Yassine Zyadi"]["initial_pin"]
    _login(other, token, credentials["Yassine Zyadi"])
    with db_session() as conn:
        conn.execute(
            "UPDATE driver_shift_distributions SET status='SUPERSEDED' WHERE id=?",
            (distribution["distribution"]["id"],),
        )
    assert other.get("/api/public/driver-shifts/me/shifts").status_code == 401


def test_new_distribution_starts_with_a_fresh_acknowledgement():
    admin, first_planning, members, _, credentials, token = _weekly_setup()
    first = _public()
    _login(first, token, credentials["Mario Rossi"])
    assert first.post("/api/public/driver-shifts/me/acknowledge").json()["acknowledged"] is True

    with db_session() as conn:
        conn.execute(
            "UPDATE driver_shift_plannings SET status='SUPERSEDED' WHERE id=?",
            (first_planning,),
        )
    second_planning = _planning(version=2, label="Settimana aggiornata")
    _add_shift(second_planning, members[0], "2026-08-17", "C9", version=2)
    second_distribution = admin.post(
        f"{BASE}/driver-shift-plannings/{second_planning}/distribution"
    ).json()
    second_id = second_distribution["distribution"]["id"]
    admin.post(f"{BASE}/driver-shift-distributions/{second_id}/credentials/prepare")
    portal = admin.post(f"{BASE}/driver-shift-distributions/{second_id}/portal").json()
    second_token = portal["access_url"].split("#token=", 1)[1]

    current = _public()
    assert _login(current, second_token, credentials["Mario Rossi"]).status_code == 200
    week = current.get("/api/public/driver-shifts/me/shifts").json()
    assert week["acknowledged"] is False
    assert week["acknowledged_at"] is None
    assert week["days"][0]["shifts"][0]["raw_shift_code"] == "C9"


def test_week_and_ack_require_a_valid_private_session():
    public = _public()
    for response in (
        public.get("/api/public/driver-shifts/me/shifts"),
        public.post("/api/public/driver-shifts/me/acknowledge"),
    ):
        assert response.status_code == 401
        assert response.text == "Sessione driver non valida."
        assert response.headers["cache-control"] == "no-store, private, max-age=0"
