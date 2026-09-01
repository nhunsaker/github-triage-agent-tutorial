"""Event schema versioning for the Queue Reader."""


class EventSchemaError(Exception):
    """Raised when an event's schema version doesn't match what this consumer expects."""


# event type -> version this consumer knows how to handle
EXPECTED_VERSIONS = {
    "order_placed": 1,
    "stock_updated": 1,
    "return_started": 1,
}


def validate(event):
    event_type = event.get("type")
    expected = EXPECTED_VERSIONS.get(event_type)
    got = event.get("version", 1)
    if expected is not None and got != expected:
        raise EventSchemaError(
            f"event schema mismatch on '{event_type}': expected v{expected} got v{got}"
        )
