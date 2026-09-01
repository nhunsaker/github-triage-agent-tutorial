"""File-backed event broker. Stands in for Kafka/SQS.

Streams are append-only JSONL files at data/queue/<stream>.jsonl. Each
consumer group tracks its own read offset in data/queue/<group>.offset so a
restarted consumer resumes where it left off instead of replaying everything.
"""
import json
import os

QUEUE_DIR = os.path.join("data", "queue")


class BrokerError(Exception):
    """Raised when the broker cannot durably record or read an event."""


def _stream_path(stream):
    return os.path.join(QUEUE_DIR, f"{stream}.jsonl")


def _offset_path(group):
    return os.path.join(QUEUE_DIR, f"{group}.offset")


def publish(stream, event):
    """Append one JSON-serializable event to a stream."""
    os.makedirs(QUEUE_DIR, exist_ok=True)
    try:
        with open(_stream_path(stream), "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError as e:
        raise BrokerError(f"failed to publish to stream '{stream}': {e}") from e


def _read_offset(group):
    path = _offset_path(group)
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    return int(content) if content else 0


def _write_offset(group, offset):
    os.makedirs(QUEUE_DIR, exist_ok=True)
    with open(_offset_path(group), "w", encoding="utf-8") as f:
        f.write(str(offset))


def consume(stream, group, batch=10):
    """Yield up to `batch` unread events for `group` from `stream`.

    The offset advances after each event is handed to the caller (i.e. as
    soon as it's yielded), so a crash mid-batch redelivers the last event.
    """
    path = _stream_path(stream)
    if not os.path.exists(path):
        return
    offset = _read_offset(group)
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    delivered = 0
    for i in range(offset, len(lines)):
        if delivered >= batch:
            break
        line = lines[i].strip()
        if not line:
            offset = i + 1
            _write_offset(group, offset)
            continue
        event = json.loads(line)
        yield event
        offset = i + 1
        _write_offset(group, offset)
        delivered += 1
