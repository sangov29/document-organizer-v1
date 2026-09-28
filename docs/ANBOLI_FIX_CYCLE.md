# Anboli feedback fix cycle

## Defect addressed

The rules classifier promoted documents on generic marker substrings such as
`invoice`, `receipt`, and `total` without requiring distinctive family
evidence. A hotel booking confirmation therefore became
`invoice_receipt` at confidence `1.0`.

## Scope

- Require distinctive evidence before assigning a known family.
- Cap generic-only evidence at the configured review threshold.
- Downweight invoice evidence when hotel/reservation anti-signals are present.
- Add bounded `schema-v0.2` fields for travel, hotel, shipping, and minimal
  legal-notice documents.
- Keep legal-notice and shipping auto-classification disabled until a broader,
  two-reviewer corpus supports promotion; their schemas remain available for
  reviewed/manual assignment.
- Require structured `Check In:` and `Check Out:` labels for automatic hotel
  promotion so prose-only reservation pages abstain.
- Treat the single hotel positive (B01-005) and single hotel abstention
  (B01-003) as smoke-test evidence only, not a training signal or validation of
  general hotel-classification capability.
- Keep annual reports out of scope and classify them as `unknown`.
- Prevent adjacent table columns and nested labels from becoming field values.
- Expand sensitivity tagging for account, travel, device, and shipping
  identifiers.
- Allow corpus fields to declare `bbox_precision` as `tight`, `region`, `page`,
  or `unresolved`.
- Define masking sensitivity as identifiers for a person, household, account,
  booking, payment, device, or shipment, with signatures and stamps treated as
  sensitive visual content.
- Record fields under an expected `unknown` family while excluding them from
  field precision/recall scoring.

## Twelve-document text-layer regression

| Document | Result | Confidence |
| --- | --- | ---: |
| B01-001 airline e-ticket | travel | 0.99 |
| B01-002 electricity bill | utility | 0.99 |
| B01-003 hotel confirmation | unknown / review | 0.50 |
| B01-004 airline receipt | travel | 0.99 |
| B01-005 Genting hotel booking | hotel | 0.99 |
| B01-006 tax invoice | invoice_receipt | 0.99 |
| B01-007 annual report | unknown / review | 0.50 |
| B01-008 GST invoice | invoice_receipt | 0.775 |
| B01-009 shipping tax invoice | invoice_receipt | 0.99 |
| B01-010 loan-default notice | unknown / review | 0.50 |
| B01-011 service invoice | invoice_receipt | 0.99 |
| B01-012 delivery order | unknown / review | 0.50 |

The GST invoice now extracts `total_amount` as `59.00` instead of the nested
label text `GST :`. The benchmark still marks the choice between the invoice
total and the overall payment amount as unresolved.

## Validation

- Backend unit and contract tests: 114 passed.
- Source review check: passed with the exact 50-ID coverage map.
- Frontend production build: passed.
- Full Docker acceptance run: not executed in the implementation environment
  because the Docker executable is unavailable.

This is a 12-document smoke test, not adoption evidence. The working corpus
retains explicit unresolved permission, value, and bounding-box items.

The success criterion is exact: B01-001, B01-002, B01-004, B01-005, B01-006,
B01-008, B01-009, and B01-011 must match their named families; B01-003,
B01-007, B01-010, and B01-012 must abstain. A known document becoming
`unknown` or incorrect is a regression, while an expected-unknown document
becoming known is a false-known failure.

Expected-unknown documents also carry diagnostic abstention reasons: B01-003
lacks the required structured stay-date labels, B01-007 is out of scope, and
B01-010/B01-012 have schemas available but automatic classification deferred.
