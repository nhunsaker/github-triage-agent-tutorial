# dashboard

Jane's Jeans store-ops UI: orders, stock on hand, and returns. Reads a
materialized snapshot that `services/qr` (the Queue Reader) writes; ships
with fixture data (`src/fixtures/materialized.sample.json`) so it renders
standalone with no backend running.

```
npm install
npm run dev
```

## Failure modes (see data/error_catalog.yaml, service: dashboard)

- **DASH-001 `StaleDataWarning`** (`src/hooks/useOrders.js`) — fires when the
  snapshot's `generated_at` is older than 5 minutes. Trigger it with
  `?stale=1`, e.g. `http://localhost:5173/?stale=1`.
- **DASH-002 `ChartRenderError`** (`src/components/StockChart.jsx`) — the
  stock bar chart reads `data.stock.series` unguarded; a snapshot missing
  the `stock` key throws the classic
  `TypeError: Cannot read properties of undefined (reading 'series')`.
  `ChartRenderErrorBoundary` catches it and re-surfaces it as
  `ChartRenderError`. Trigger it with `?emptyStock=1`, which swaps in
  `src/fixtures/materialized.emptystock.sample.json`.
- **DASH-003 `FilterStateError`** (`src/state/filters.js`) — thrown by
  `validateFilters` on an impossible combination (e.g. `status: cancelled`
  + `returnsOnly: true`, or a date range with `dateFrom` after `dateTo`).
  Trigger it in the UI by setting Status to "Cancelled" and checking
  "Returns only".
