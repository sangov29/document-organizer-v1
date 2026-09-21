from sqlalchemy import text

from app.db.session import engine
from app.services.rate_limiter import rate_limiter
from app.services.storage import storage


def dependency_readiness() -> dict[str, str]:
    """Return sanitized dependency state without exposing exception details."""
    checks: dict[str, str] = {}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"

    try:
        checks["redis"] = "ok" if rate_limiter.client.ping() else "unavailable"
    except Exception:
        checks["redis"] = "unavailable"

    try:
        storage.client.head_bucket(Bucket=storage.bucket)
        checks["object_storage"] = "ok"
    except Exception:
        checks["object_storage"] = "unavailable"

    return checks
