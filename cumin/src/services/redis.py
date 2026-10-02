import time

from redis import Redis


class RedisRateLimiter:
    """Fixed one-minute window stored in Redis. Same allow() shape as RateLimiter."""

    def __init__(self, url: str) -> None:
        self._redis = Redis.from_url(url)

    def allow(self, tenant_id: str, requests_per_minute: int, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        bucket = int(current // 60)
        key = f"cumin:rl:{tenant_id}:{bucket}"
        count = int(self._redis.incr(key))
        if count == 1:
            self._redis.expire(key, 70)
        return count <= requests_per_minute

    def current(self, tenant_id: str, now: float | None = None) -> int:
        moment = time.time() if now is None else now
        value = self._redis.get(f"cumin:rl:{tenant_id}:{int(moment // 60)}")
        return 0 if value is None else int(value)
