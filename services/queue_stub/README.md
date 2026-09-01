# queue_stub

A tiny file-backed event broker. Stands in for Kafka/SQS so the tutorial needs
zero external accounts and zero running server processes.

- `publish(stream, event)` appends a JSON line to `data/queue/<stream>.jsonl`.
- `consume(stream, group, batch)` is a generator that yields unread events for
  a consumer group, tracking its offset in `data/queue/<group>.offset`.

No server, no daemon. `services/api` publishes to it directly; `services/qr`
consumes from it directly, both as plain function calls against the
filesystem.

Failure mode: `BrokerError`, raised on I/O failure. It isn't a catalog entry
itself (the queue is infrastructure, not a Jane's Jeans service) but
`services/api/events.py` wraps it into `EventPublishError`.
