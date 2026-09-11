# Audit Export Schema — `audit-export-v0.1`

The owner audit API and JSON download use a versioned envelope so retained
events remain interpretable as the product schema evolves.

## Envelope

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | Always `audit-export-v0.1` for this contract. |
| `events` | array | Newest-first immutable audit facts owned by the authenticated user. |

## Event

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | UUID string | Stable audit-event identifier. |
| `event_type` | string | `upload`, `duplicate_override`, `correction`, `confirmation`, `sensitive_reveal`, or `deletion`. |
| `target_type` | string | Domain subject: `document`, `extracted_field`, or `visual_region`. |
| `target_id` | string/null | Historical subject identifier. It may reference a permanently deleted subject and is not a live-resource guarantee. |
| `metadata` | object | Event-specific, value-free context. It must never contain passwords, tokens, revealed values, document text, or image content. |
| `created_at` | RFC 3339 timestamp | Server-recorded event time. |

## Stability and privacy

- Events are append-only; the API provides no mutation or deletion route.
- Permanent document deletion retains only its audit fact and non-content
  cleanup count. Source names, hashes, extracted values and object keys are not
  copied into the deletion event.
- Unknown fields may be added only in a later schema version. Consumers must
  reject an unsupported major version and tolerate additive minor-version
  fields.
- Exports are owner-scoped and returned with `Cache-Control: no-store, private`.
