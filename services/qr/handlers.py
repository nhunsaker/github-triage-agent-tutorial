"""Per-event-type handling plus poison-message retry logic."""
from services.qr import dlq, schema


class PoisonMessageError(Exception):
    """Raised when an event fails processing repeatedly and gets dead-lettered."""


MAX_ATTEMPTS = 3


def handle(event, materialized):
    """Process one event, retrying up to MAX_ATTEMPTS on failure before dead-lettering.

    Schema mismatches are not retried, they're a distinct catalog failure mode
    (EventSchemaError) and retrying won't fix a version mismatch.
    """
    schema.validate(event)

    attempts = 0
    last_error = None
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        try:
            _apply(event, materialized)
            return
        except Exception as e:
            last_error = e

    dlq.add(event, str(last_error))
    raise PoisonMessageError(
        f"poison message rejected after {attempts} attempts: event {event.get('id', '?')}"
    )


def _apply(event, materialized):
    event_type = event.get("type")
    if event_type == "order_placed":
        materialized["order_count"] = materialized.get("order_count", 0) + 1
    elif event_type == "stock_updated":
        materialized["stock_updates"] = materialized.get("stock_updates", 0) + 1
    elif event_type == "return_started":
        materialized["returns"] = materialized.get("returns", 0) + 1
    elif event_type == "__force_fail__":
        # test/demo hook for exercising the poison-message path deliberately
        raise ValueError("forced failure for testing the poison-message path")
    # unknown-but-schema-valid event types are silently counted as no-ops;
    # this is a teaching stub, not a production consumer
