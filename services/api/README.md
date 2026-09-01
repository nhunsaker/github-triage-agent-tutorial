# api

FastAPI app for Jane's Jeans orders, inventory, and returns. In-memory state,
no database.

Run: `uvicorn services.api.main:app --reload` then hit `/health`,
`POST /orders`, `GET /stock/{sku}`, `POST /returns`.

Failure modes (see `data/error_catalog.yaml`):

- `inventory.OversellError` — reserving more stock than is on hand.
- `orders.OrderValidationError` — missing sku / bad quantity.
- `orders.CheckoutError` — checkout hit an internal error (e.g. an unknown
  sku slipped past validation).
- `events.EventPublishError` — publishing an order event to the internal
  queue (`services/queue_stub`) failed.
- `returns.ReturnStateError` — an action isn't valid for the return's state.
