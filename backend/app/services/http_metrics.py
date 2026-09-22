"""Bounded, process-local HTTP counters for the metrics scrape endpoint.

Only application route templates and response classes become labels. Paths,
queries, headers, document identifiers and exception messages are never stored.
"""

from collections import defaultdict
from threading import Lock
from time import monotonic


BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class HttpMetrics:
    def __init__(self):
        self._lock = Lock()
        self._totals = defaultdict(int)
        self._durations = defaultdict(float)
        self._buckets = defaultdict(int)

    def observe(self, route: str, status_code: int, seconds: float) -> None:
        # Route is supplied by the router, never from request.url.path.
        key = (route, f"{status_code // 100}xx")
        elapsed = max(0.0, seconds)
        with self._lock:
            self._totals[key] += 1
            self._durations[key] += elapsed
            for bound in BUCKETS:
                if elapsed <= bound:
                    self._buckets[key, bound] += 1

    def render(self) -> str:
        lines = [
            "# HELP document_http_requests_total HTTP requests by route template and status class.",
            "# TYPE document_http_requests_total counter",
            "# HELP document_http_request_duration_seconds HTTP request duration.",
            "# TYPE document_http_request_duration_seconds histogram",
        ]
        with self._lock:
            for (route, status_class), count in sorted(self._totals.items()):
                labels = f'route="{_label(route)}",status_class="{status_class}"'
                lines.append(f"document_http_requests_total{{{labels}}} {count}")
                for bound in BUCKETS:
                    lines.append(
                        f'document_http_request_duration_seconds_bucket{{{labels},le="{bound:g}"}} '
                        f'{self._buckets[(route, status_class), bound]}'
                    )
                lines.append(f'document_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {count}')
                lines.append(f'document_http_request_duration_seconds_sum{{{labels}}} '
                             f'{self._durations[(route, status_class)]:.9f}')
                lines.append(f'document_http_request_duration_seconds_count{{{labels}}} {count}')
        return "\n".join(lines) + "\n"


http_metrics = HttpMetrics()


async def record_http_metrics(request, call_next):
    started = monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        # Skip scrapes and aggregate missing routes into one bounded label.
        # Never use the raw request path as a fallback.
        route = request.scope.get("route")
        template = getattr(route, "path", None) or "_unmatched"
        if request.url.path != "/internal/metrics":
            http_metrics.observe(template, status_code, monotonic() - started)
