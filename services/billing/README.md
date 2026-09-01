# billing

PayFlow integration for Jane's Jeans: charges, refunds, webhook verification.
`vendor_stub.py` is a local fake of PayFlow, no network calls, no vendor
account. Script its failures with `PAYFLOW_MODE=outage|declined|v2_cutover|
bad_signature` or by passing `mode=` directly to `payflow.charge`/`refund`.

Failure modes (see `data/error_catalog.yaml`):

- `payflow.PayFlowUnavailableError` — vendor outage (503).
- `payflow.PayFlowDeprecationError` — v1 endpoint hit after v2 cutover
  (year-2-only drift case).
- `webhooks.WebhookVerificationError` — signature didn't verify.
- `refunds.RefundDeclinedError` — vendor declined a refund.
- `charges.DuplicateChargeError` — same order charged twice.
