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
latency histogram over time.

## Acceptance SLO gate

The acceptance workflow now evaluates the accumulated synthetic API traffic
after functional, timing and browser tests. It publishes `slo-evaluation.json`
and `junit-slo.xml` and fails the workflow unless all of these hold:

- dependency readiness is healthy;
- at least 100 `/api/v1/` requests were observed;
- the API 5xx ratio is at most 1%;
- the histogram upper bound for successful-request p95 latency is at most 2.5 seconds.

These are repeatable release-regression targets for the Docker acceptance
environment. They are not a production availability or latency commitment.
Production SLOs and paging thresholds require a representative load baseline,
an agreed measurement window, maintenance exclusions and an error-budget
policy. Worker queue age, backup retention and production restore objectives
also remain separate gates. The isolated acceptance restore probe validates
content integrity but does not establish a production backup policy or recovery
objective.
