import base64

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


def upload_required_evidence(client, base: str, opened: dict, suffix: str = "required") -> None:
    headers = {"X-Journal-Token": opened["token"]}
    for checkpoint in ("CHECK_IN", "CHECK_OUT"):
        started = client.post(
            f"{base}/sessions/{opened['id']}/checkpoints/{checkpoint}/start",
            headers=headers,
            json={"mode": "VIDEO"},
        )
        if started.status_code == 409 and "già completato" in started.text:
            continue
        assert started.status_code == 200, started.text
        response = client.post(
            f"{base}/sessions/{opened['id']}/media",
            headers=headers,
            data={
                "checkpoint": checkpoint,
                "evidence_mode": "VIDEO",
                "evidence_slot": "VIDEO",
                "capture_source": "camera",
            },
            files={"file": (
                f"{suffix}-{checkpoint}.mp4",
                MP4 + f"{suffix}-{checkpoint}".encode(),
                "video/mp4",
            )},
        )
        assert response.status_code == 201, response.text
        completed = client.post(
            f"{base}/sessions/{opened['id']}/checkpoints/{checkpoint}/complete",
            headers=headers,
        )
        assert completed.status_code == 200, completed.text
