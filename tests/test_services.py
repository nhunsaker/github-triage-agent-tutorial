"""Exercises every error_catalog.yaml symbol on a real failure path.

Run: python -m pytest tests/ -q
"""
import pytest

from services.api import events, inventory, orders, returns
from services.billing import charges, payflow, refunds, webhooks
from services.qr import consumer, dlq, handlers, schema
from services.queue_stub import broker


# ── api ──────────────────────────────────────────────────────────────────

def test_oversell_error():
    with pytest.raises(inventory.OversellError):
        inventory.reserve("JJ-720-28", 1)  # seeded at 0 on hand


def test_order_validation_error():
    with pytest.raises(orders.OrderValidationError):
        orders.place_order({"sku": "", "quantity": 1})


def test_checkout_error_on_unknown_sku():
    with pytest.raises(orders.CheckoutError):
        orders.place_order({"sku": "NOT-A-REAL-SKU", "quantity": 1})


def test_return_state_error():
    ret = returns.start_return(order_id=1)
    with pytest.raises(returns.ReturnStateError):
        returns.advance(ret["id"], "refund")  # can't refund before approval


def test_event_publish_error(monkeypatch):
    def boom(stream, event):
        raise broker.BrokerError("disk full")

    monkeypatch.setattr(broker, "publish", boom)
    with pytest.raises(events.EventPublishError):
        events.publish("orders", {"type": "order_placed"})


def test_api_endpoints():
    from fastapi.testclient import TestClient

    from services.api.main import app

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    resp = client.post("/orders", json={"sku": "JJ-720-28", "quantity": 5})
    assert resp.status_code == 409


# ── qr ───────────────────────────────────────────────────────────────────

def test_event_schema_error():
    with pytest.raises(schema.EventSchemaError):
        schema.validate({"type": "order_placed", "version": 99})


def test_poison_message_and_dead_letter():
    dlq.drain()
    with pytest.raises(handlers.PoisonMessageError):
        handlers.handle({"id": "e1", "type": "__force_fail__"}, {})
    assert dlq.size() == 1


def test_dead_letter_overflow():
    dlq.drain()
    for i in range(dlq.DLQ_THRESHOLD):
        dlq.add({"id": i}, "test")
    with pytest.raises(dlq.DeadLetterOverflow):
        dlq.add({"id": "one-too-many"}, "test")


def test_consumer_lag_warning():
    with pytest.warns(consumer.ConsumerLagWarning):
        consumer.check_lag({"published_at": 0}, now=1000)


def test_duplicate_event_warning():
    seen = {"e1"}
    with pytest.warns(consumer.DuplicateEventWarning):
        consumer.check_duplicate({"id": "e1"}, seen)


def test_consumer_run_once_drains_stream(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    broker.publish("orders", {"id": "a", "type": "order_placed"})
    broker.publish("orders", {"id": "b", "type": "order_placed"})
    result = consumer.run_once()
    assert result["order_count"] == 2


# ── billing ──────────────────────────────────────────────────────────────

def test_payflow_unavailable_error():
    with pytest.raises(payflow.PayFlowUnavailableError):
        payflow.charge("order-1", 100, mode="outage")


def test_payflow_deprecation_error():
    with pytest.raises(payflow.PayFlowDeprecationError):
        payflow.charge("order-1", 100, mode="v2_cutover")


def test_refund_declined_error():
    with pytest.raises(refunds.RefundDeclinedError):
        refunds.refund_order("order-1", mode="declined")


def test_webhook_verification_error():
    with pytest.raises(webhooks.WebhookVerificationError):
        webhooks.handle_webhook({}, "bad-signature", "delivery-1", mode="bad_signature")


def test_duplicate_charge_error():
    charges.charge_order("order-dup", 100)
    with pytest.raises(charges.DuplicateChargeError):
        charges.charge_order("order-dup", 100)


# ── queue_stub itself ────────────────────────────────────────────────────

def test_broker_publish_and_consume_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    broker.publish("test-stream", {"n": 1})
    broker.publish("test-stream", {"n": 2})
    seen = list(broker.consume("test-stream", "test-group", batch=10))
    assert [e["n"] for e in seen] == [1, 2]
    # offset persisted: a second consume call with no new events yields nothing
    assert list(broker.consume("test-stream", "test-group", batch=10)) == []
