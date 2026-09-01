"""The Queue Reader: consumes the 'orders' stream, materializes counts to disk.

    python -m services.qr.consumer --once

drains whatever is currently on the stream and exits (no daemon/watch loop).
"""
import argparse
import json
import os
import time
import warnings

from services.qr import handlers
from services.queue_stub import broker

STREAM = "orders"
GROUP = "qr"
MATERIALIZED_PATH = os.path.join("data", "materialized", "orders.json")
LAG_THRESHOLD_SECONDS = 30


class ConsumerLagWarning(Warning):
    """Warned when the consumer falls behind the stream by more than the threshold."""


class DuplicateEventWarning(Warning):
    """Warned when an event id has already been materialized."""


def _load_materialized():
    if os.path.exists(MATERIALIZED_PATH):
        with open(MATERIALIZED_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_materialized(materialized):
    os.makedirs(os.path.dirname(MATERIALIZED_PATH), exist_ok=True)
    with open(MATERIALIZED_PATH, "w", encoding="utf-8") as f:
        json.dump(materialized, f, indent=2)


def check_lag(event, now=None):
    """Warn if an event's publish time is more than LAG_THRESHOLD_SECONDS in the past."""
    published_at = event.get("published_at")
    if published_at is None:
        return
    now = time.time() if now is None else now
    lag = now - published_at
    if lag > LAG_THRESHOLD_SECONDS:
        warnings.warn(
            f"consumer lag exceeded {int(lag)}s on stream '{STREAM}'",
            ConsumerLagWarning,
        )


def check_duplicate(event, seen_ids):
    """Returns True (and warns) if this event id was already materialized."""
    event_id = event.get("id")
    if event_id is None:
        return False
    if event_id in seen_ids:
        warnings.warn(
            f"duplicate delivery detected for event {event_id}, skipping",
            DuplicateEventWarning,
        )
        return True
    seen_ids.add(event_id)
    return False


def run_once(batch=50):
    """Drain whatever is currently on the stream once, then return the materialized state."""
    materialized = _load_materialized()
    seen_ids = set(materialized.get("_seen_ids", []))

    for event in broker.consume(STREAM, GROUP, batch=batch):
        check_lag(event)
        if check_duplicate(event, seen_ids):
            continue
        try:
            handlers.handle(event, materialized)
        except handlers.PoisonMessageError:
            continue  # already dead-lettered inside handlers.handle

    materialized["_seen_ids"] = list(seen_ids)
    _save_materialized(materialized)
    return materialized


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True)
    parser.parse_args()
    result = run_once()
    print(json.dumps(result, indent=2))
