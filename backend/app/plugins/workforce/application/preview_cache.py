from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable

from app.plugins.workforce.importer.workbook_interpreter import (
    ParsedWorkforceWorkbook,
)


@dataclass(frozen=True)
class _CacheEntry:
    parsed: ParsedWorkforceWorkbook
    expires_at: float


class WorkforcePreviewCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 900,
        max_entries: int = 4,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive.")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive.")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = Lock()

    def _evict_expired(self, now: float) -> None:
        expired = [
            fingerprint
            for fingerprint, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for fingerprint in expired:
            self._entries.pop(fingerprint, None)

    def store(self, parsed: ParsedWorkforceWorkbook) -> None:
        now = self._clock()
        with self._lock:
            self._evict_expired(now)
            self._entries.pop(parsed.fingerprint, None)
            self._entries[parsed.fingerprint] = _CacheEntry(
                parsed=parsed,
                expires_at=now + self._ttl_seconds,
            )
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def get(self, fingerprint: str) -> ParsedWorkforceWorkbook | None:
        now = self._clock()
        with self._lock:
            self._evict_expired(now)
            entry = self._entries.get(fingerprint)
            if entry is None:
                return None
            self._entries.move_to_end(fingerprint)
            return entry.parsed

    def discard(self, fingerprint: str) -> None:
        with self._lock:
            self._entries.pop(fingerprint, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
