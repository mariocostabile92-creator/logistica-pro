import base64

from app.core.database import db_session


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


def upload_required_evidence(client, base: str, opened: dict, suffix: str = "required") -> None:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT media_type FROM movement_media WHERE session_id = ?",
            (opened["id"],),
        ).fetchall()
    present = {row["media_type"] for row in rows}
    headers = {"X-Journal-Token": opened["token"]}
    if "image" not in present:
        response = client.post(
            f"{base}/sessions/{opened['id']}/media",
            headers=headers,
            files={"file": (f"{suffix}.png", PNG + suffix.encode(), "image/png")},
        )
        assert response.status_code == 201, response.text
    if "video" not in present:
        response = client.post(
            f"{base}/sessions/{opened['id']}/media",
            headers=headers,
            files={"file": (f"{suffix}.mp4", MP4 + suffix.encode(), "video/mp4")},
        )
        assert response.status_code == 201, response.text
