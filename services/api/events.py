"""Publishes domain events onto the internal queue for Jane's Jeans."""
from services.queue_stub import broker


class EventPublishError(Exception):
    """Raised when publishing an event to the queue fails."""


def publish(stream, event):
    try:
        broker.publish(stream, event)
    except broker.BrokerError as e:
        event_type = event.get("type", "unknown")
        raise EventPublishError(
            f"failed to publish '{event_type}' to stream '{stream}'"
        ) from e
