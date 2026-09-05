import redis
from app.core.config import settings


class SessionStore:
    def __init__(self):
        self.client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.ttl_seconds = settings.idle_session_minutes * 60

    @staticmethod
    def _key(session_id: str) -> str:
        return f"auth:session:{session_id}"

    @staticmethod
    def _user_sessions_key(user_id: str) -> str:
        return f"auth:user_sessions:{user_id}"

    def create(self, session_id: str, user_id: str) -> None:
        pipe = self.client.pipeline()
        pipe.set(self._key(session_id), user_id, ex=self.ttl_seconds)
        pipe.sadd(self._user_sessions_key(user_id), session_id)
        # Keep the reverse index only as long as sessions can plausibly live.
        pipe.expire(self._user_sessions_key(user_id), self.ttl_seconds)
        pipe.execute()

    def touch(self, session_id: str, user_id: str) -> bool:
        key = self._key(session_id)
        stored_user_id = self.client.get(key)
        if stored_user_id != user_id:
            return False
        pipe = self.client.pipeline()
        pipe.expire(key, self.ttl_seconds)
        pipe.sadd(self._user_sessions_key(user_id), session_id)
        pipe.expire(self._user_sessions_key(user_id), self.ttl_seconds)
        pipe.execute()
        return True

    def revoke(self, session_id: str) -> None:
        key = self._key(session_id)
        user_id = self.client.get(key)
        pipe = self.client.pipeline()
        pipe.delete(key)
        if user_id:
            pipe.srem(self._user_sessions_key(user_id), session_id)
        pipe.execute()

    def revoke_all(self, user_id: str) -> int:
        reverse_key = self._user_sessions_key(user_id)
        session_ids = list(self.client.smembers(reverse_key))
        if not session_ids:
            self.client.delete(reverse_key)
            return 0
        pipe = self.client.pipeline()
        for session_id in session_ids:
            pipe.delete(self._key(session_id))
        pipe.delete(reverse_key)
        pipe.execute()
        return len(session_ids)


session_store = SessionStore()
