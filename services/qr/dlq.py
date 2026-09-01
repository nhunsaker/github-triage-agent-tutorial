"""Dead-letter queue for events the consumer could not process."""

DLQ_THRESHOLD = 10


class DeadLetterOverflow(Exception):
    """Raised when the dead-letter queue grows past the threshold."""


_dead_letters = []


def add(event, reason):
    _dead_letters.append({"event": event, "reason": reason})
    if len(_dead_letters) > DLQ_THRESHOLD:
        raise DeadLetterOverflow(
            f"dead-letter queue above threshold: {len(_dead_letters)} events waiting"
        )


def size():
    return len(_dead_letters)


def drain():
    """Test/ops hook: clear the dead-letter queue."""
    _dead_letters.clear()
