import hashlib

import redis

from app.core.config import settings


class RateLimiter:
    _HIT_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return count
    """

    def __init__(self):
        self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    @staticmethod
    def key(scope: str, subject: str) -> str:
        digest = hashlib.sha256(subject.strip().lower().encode()).hexdigest()
        return f"auth:rate:{scope}:{digest}"

    def allowed(self, scope: str, subject: str, limit: int, window_seconds: int) -> bool:
        count = int(self.client.eval(self._HIT_SCRIPT, 1, self.key(scope, subject), window_seconds))
        return count <= limit

    def clear(self, scope: str, subject: str) -> None:
        self.client.delete(self.key(scope, subject))


rate_limiter = RateLimiter()
