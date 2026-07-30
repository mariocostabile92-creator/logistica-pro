from dataclasses import dataclass


@dataclass(frozen=True)
class JournalSharedAccess:
    id: str
    token: str
    status: str
    created_at: str
    revoked_at: str | None = None
    last_used_at: str | None = None

