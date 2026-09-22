# Operational monitoring foundation

Set a high-entropy `METRICS_TOKEN` in the backend environment and scrape
`GET /internal/metrics` with the `X-Metrics-Token` header from a restricted
monitoring network. When the token is unset, the endpoint returns 404. Missing
and incorrect tokens return the same 404. Do not put the token in a URL, scrape
configuration committed to Git, or a public dashboard.

The endpoint emits request counts and duration histograms by FastAPI route
**template** and response status **class**. It records no account identifiers,
document IDs, query strings, request/response bodies, headers or exception
messages. Unmatched paths share `_unmatched`. Metrics are process-local and reset
when the API restarts; sum across API instances in the monitoring system.
Scrapes themselves are excluded. The existing `/health/live` and
`/health/ready` remain separate process and dependency probes.

For an external monitor, track readiness failures, the 5xx fraction and
latency histogram over time. Do not turn a passing synthetic acceptance run
into a production availability or latency claim. Numeric SLOs, alert
thresholds, worker queue age, backup retention, restore time, and production
traffic budgets still require an owner-approved load and operations baseline.
The isolated acceptance restore probe validates content integrity but does not
establish a production backup policy or recovery objective.
