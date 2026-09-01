# qr — the Queue Reader

A plain-Python worker (no FastAPI) that consumes the `orders` stream from
`services/queue_stub` and materializes order/stock/return counts to
`data/materialized/orders.json`.

Run once and exit: `python -m services.qr.consumer --once`. No daemon, no
watch loop, by design.

Failure modes (see `data/error_catalog.yaml`):

- `consumer.ConsumerLagWarning` — the consumer is falling behind the stream.
- `consumer.DuplicateEventWarning` — an event id was already materialized.
- `handlers.PoisonMessageError` — an event failed 3 processing attempts and
  got dead-lettered.
- `dlq.DeadLetterOverflow` — the dead-letter queue grew past its threshold.
- `schema.EventSchemaError` — an event's version doesn't match what this
  consumer expects (usually caused by an `api` deploy shipping a new shape).
