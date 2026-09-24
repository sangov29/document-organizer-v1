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

## Controlled load qualification

After the functional and browser journeys, the workflow creates a fresh
verified synthetic account and sends 240 authenticated read requests at
concurrency 8. The mix is 75% document listing and 25% paginated organization
search. The gate requires:

- no more than 1% non-2xx responses;
- no more than 1% 5xx responses;
- no unexpected HTTP 429 responses;
- p95 request latency no greater than 1.0 second;
- throughput of at least 10 requests per second.

Results are published in `load-qualification.json` and `junit-load.xml`. This is
a small, controlled CI regression profile for authenticated database/Redis
reads. It is not a stress test, soak test, capacity ceiling or production sizing
claim. Production qualification still needs representative document volumes,
multiple API replicas, write/OCR mixes, longer duration and agreed traffic
forecasts.

## Rate-limit and browser security validation

The acceptance stack pins TOTP confirmation to three attempts in a two-second
window so the public API can prove threshold enforcement, `Retry-After`,
per-account isolation and recovery without waiting for the production default
five-minute window. Share-link throttling separately proves per-token isolation,
malformed-token handling and recovery. Login timing uses an explicit high
acceptance-only ceiling because its distribution probe deliberately performs
hundreds of failed requests; production retains the configured default.

Both API and frontend responses enforce `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a restrictive
camera/microphone/geolocation `Permissions-Policy`. Runtime tests verify the API
headers and the Playwright journey verifies the browser document response.
