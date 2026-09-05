from __future__ import annotations

import os
import time
import httpx

API_HEALTH = os.getenv("ACCEPTANCE_HEALTH_URL", "http://localhost:8000/health")
MAILPIT = os.getenv("MAILPIT_API_URL", "http://mailpit:8025")


def wait(url: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=3.0)
            if response.status_code < 500:
                return
            last = f"status={response.status_code}"
        except Exception as exc:
            last = repr(exc)
        time.sleep(1)
    raise SystemExit(f"health wait failed for {url}: {last}")


wait(API_HEALTH)
wait(f"{MAILPIT}/api/v1/")
print("acceptance dependencies healthy")
