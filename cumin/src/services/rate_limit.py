import threading
import time


class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, tenant_id: str, requests_per_minute: int, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        with self._lock:
            recent = [hit for hit in self._hits.get(tenant_id, []) if current - hit < 60]
            if len(recent) >= requests_per_minute:
                self._hits[tenant_id] = recent
                return False
            recent.append(current)
            self._hits[tenant_id] = recent
            return True

    def current(self, tenant_id: str, now: float | None = None) -> int:
        moment = time.monotonic() if now is None else now
        with self._lock:
            return sum(1 for hit in self._hits.get(tenant_id, []) if moment - hit < 60)
