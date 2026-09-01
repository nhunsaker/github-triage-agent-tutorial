# 1. The product

Everything downstream, the corpus, the rulebook, the investigation, reads
issues about a fictional company called Jane's Jeans, an online jeans
store. This layer is the tour: clone it, run the pieces that run, and
meet `data/error_catalog.yaml`, the file every other layer keys off.

## Do this: clone and look around

```
git clone <this repo>
cd github-triage-agent-tutorial
pip install -r requirements.txt
python -m pytest tests/ -q
```

```
........................                                                 [100%]
24 passed in 0.63s
```

24 tests, all green, on a fresh clone. Two of those tests matter for this
layer specifically: they check that every entry in the error catalog
points at a file and a symbol that actually exist in `services/`. More on
that below.

## The four services

Jane's Jeans is a small monorepo under `services/`. Order and inventory
activity flows through an internal event queue, a file-backed stub, so
the four services have the same seams a real event-driven backend has:
one service publishes, another consumes, and a UI reads what got
materialized.

### `services/api`: orders and inventory

FastAPI, in-memory state, no database. Run it with
`uvicorn services.api.main:app --reload`, then hit `/health`,
`POST /orders`, `GET /stock/{sku}`, `POST /returns`.

Look at `services/api/inventory.py`. Stock is a plain dict seeded with
four skus, one of them, `JJ-720-28`, seeded at zero on purpose because
it's the sku the demo issues hit. `reserve()` decrements on hand stock
and raises `OversellError` if a reservation would push it negative:

```python
def reserve(sku, quantity):
    on_hand = STOCK[sku]
    if on_hand - quantity < 0:
        raise OversellError(
            f"stock below zero for sku {sku}: reserved {quantity}, on hand {on_hand}"
        )
    STOCK[sku] = on_hand - quantity
    return STOCK[sku]
```

That message string is not incidental. It is quoted, verbatim modulo the
filled in variables, in the error catalog entry for this failure mode,
and issues in the corpus quote it too. Chase that thread far enough and
you land on the exact line above.

`services/api/main.py` wires three more failure modes into HTTP status
codes: `OrderValidationError` becomes a 422, `OversellError` becomes a
409, `CheckoutError` becomes a 500. `services/api/events.py` publishes
order events to the queue and raises `EventPublishError` if that publish
fails. `services/api/returns.py` raises `ReturnStateError` when you try
to advance a return through an action that isn't valid for its current
state.

### `services/qr`: the Queue Reader

A plain Python worker, no FastAPI, no daemon. Run it once and it exits:
`python -m services.qr.consumer --once`. It consumes the `orders` stream
from `services/queue_stub` and materializes order, stock, and return
counts to `data/materialized/orders.json`, which is the file
`services/dashboard` reads.

Its failure modes live in three files: `consumer.py` raises
`ConsumerLagWarning` when the consumer falls behind the stream and
`DuplicateEventWarning` when an event id was already materialized,
`handlers.py` raises `PoisonMessageError` after an event fails three
processing attempts, and `dlq.py` raises `DeadLetterOverflow` when the
dead-letter queue grows past its threshold. `schema.py` adds a fifth,
`EventSchemaError`, usually caused by an api deploy shipping a new event
shape that qr does not expect yet.

That last one is the point of the queue existing at all: a schema change
in `api` surfaces as a failure in `qr`, and "orders stuck" can genuinely
be either service's fault. The corpus generates cases exactly like this
on purpose, more in the next layer.

### `services/dashboard`: the store-ops UI

A small React app, plain JavaScript, reads the snapshot `qr` writes and
ships with fixture data so it renders standalone with no backend running.

```
cd services/dashboard
npm install
npm run dev
```

Three failure modes, each with a way to trigger it locally.
`StaleDataWarning` fires when the snapshot's `generated_at` is older than
five minutes, trigger it with `?stale=1`. `ChartRenderError` comes from
`StockChart.jsx` reading `data.stock.series` unguarded, a snapshot
missing the `stock` key throws the classic
`TypeError: Cannot read properties of undefined (reading 'series')`,
trigger it with `?emptyStock=1`. `FilterStateError` comes from
`validateFilters` rejecting an impossible combination, like status
cancelled plus returns-only, trigger it in the UI directly.

Read the `StaleDataWarning` trigger again: a stale banner on the
dashboard looks like a dashboard bug. It usually is not. It usually means
`qr` fell behind, which is `ConsumerLagWarning`, several files away. This
is the same ambiguity as the qr and api overlap above, now with a third
service in the mix.

### `services/billing`: the PayFlow integration

PayFlow is the fictional payment vendor, and `vendor_stub.py` is a local
fake of it: no network calls, no vendor account. You script its behavior
with an environment variable or a direct argument:

```python
def charge(order_id, amount, mode=None):
    m = _mode(mode)
    if m == "outage":
        raise VendorOutageError("PayFlow API unreachable: 503 from /v1/charges")
    if m == "v2_cutover":
        raise DeprecatedEndpointError("/v1/charges")
    if m == "declined":
        return {"status": "declined", "code": "insufficient_funds"}
    return {"status": "approved", "order_id": order_id, "amount": amount}
```

`PAYFLOW_MODE=outage|declined|v2_cutover|bad_signature` picks the
behavior. `services/billing/webhooks.py` builds on the stub the same way
every other service builds on its failure modes: it calls
`vendor_stub.verify_webhook_signature`, and if that comes back false it
raises `WebhookVerificationError` with the delivery id baked into the
message.

```python
def handle_webhook(payload, signature, delivery_id, mode=None):
    if not vendor_stub.verify_webhook_signature(payload, signature, mode=mode):
        raise WebhookVerificationError(
            f"webhook signature verification failed for delivery {delivery_id}"
        )
    return {"status": "ok"}
```

Billing is the service whose issues route external most often, vendor
outages, webhook changes, API deprecations, which is what makes the
internal versus external routing lesson real starting in layer 3.

## The queue stub

`services/queue_stub` is the plumbing under `api` and `qr`, not a Jane's
Jeans service itself, so it has no entry in the error catalog. It is a
tiny file-backed broker: `publish(stream, event)` appends a JSON line to
`data/queue/<stream>.jsonl`, `consume(stream, group, batch)` is a
generator that yields unread events for a consumer group and tracks its
offset in a sibling file. No server process, no daemon, both `api` and
`qr` call it as plain functions against the filesystem.

It raises one thing, `BrokerError`, on I/O failure. `api`'s `events.py`
catches that and wraps it into `EventPublishError`, which does have a
catalog entry. That wrapping is the pattern to notice: the queue is
infrastructure, the catalog only tracks failures the services themselves
surface.

## The error catalog

Open `data/error_catalog.yaml`. Every failure mode across all four
services is one entry:

```yaml
- id: API-001
  service: api
  file: services/api/inventory.py
  symbol: OversellError
  message: "stock below zero for sku {sku}: reserved {reserved}, on hand {on_hand}"
  severity: S1
  routing: internal
  weight: 6
  notes: race condition under load. flash-sale clusters use this.
```

`id`, `service`, `file`, and `symbol` tie the entry to real code. `file`
and `symbol` are load-bearing, not documentation: `tests/test_corpus.py`
asserts every catalog file exists and every catalog symbol appears in it.

```python
def test_catalog_symbols_exist_in_named_file():
    bad = []
    for e in load_catalog():
        path = ROOT / e["file"]
        if not path.exists():
            bad.append((e["id"], "file missing"))
            continue
        if e["symbol"] not in path.read_text():
            bad.append((e["id"], f"{e['symbol']} not in {e['file']}"))
    assert not bad, f"catalog symbols missing from code: {bad}"
```

`message` is a template. `{vars}` get filled in by the corpus generator
and by the running services, and the literal, non-variable parts of that
template are what shows up quoted in issue bodies and in real log lines
alike. `severity` and `routing` are the typical values for this failure,
S0 through S3 and internal, external, or human, both explained in full in
layer 3. `weight` sets how often the corpus generator picks this entry
relative to the others. `year2_only`, on one entry only, `BILL-004`,
marks a failure that never appears in year 1 of the corpus, the drift
case layer 3 and layer 8 both build on.

This coupling is the spine of the whole tutorial. Services implement
exactly these failure modes at exactly these files and symbols. The
corpus generator emits issues quoting these signatures. The rulebook you
train in layer 3 keys its rules off them. The investigation in layer 5
greps for them and finds real code, not a hallucinated file path.

Here is why that matters more than it looks like it should. In a real
codebase, your error catalog is not a YAML file, it is your actual
exception classes and the log lines they produce. You do not maintain a
separate list of "here are our failure modes," the exceptions are the
list. This tutorial makes that list a literal file you can open and read
because a fictional company generating fictional issues needs one place
that both the issue generator and the services agree on. Read
`data/error_catalog.yaml` as a stand-in for "grep your codebase for raise
statements," not as a pattern to copy into your own repo.

## Checkpoint

You should now be able to name all four services, say what each one's
job is, and point to the file and symbol behind at least two failure
modes without looking them up. Run `python -m pytest tests/ -q` again if
you have not, all 24 should pass. Layer 2 loads two years of issues built
from this catalog and starts mining them for patterns.

## the heavy version

If Jane's Jeans grew from four services to forty, it would stop reading a
YAML file to know what can go wrong. It would read the actual exception
hierarchy and log schema across every one of those services, and a
trained model, not a lookup table, would learn which quoted signatures
predict which outcomes. The coupling this layer teaches, catalog entry to
real file and symbol, is the same coupling that model would depend on:
garbage in the training signal produces garbage routing, whether the
signal comes from a YAML file a human wrote or a log pipeline scraping
forty services worth of production traffic.
