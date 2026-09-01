// Filter state for the store-ops dashboard's OrdersPanel/ReturnsPanel.
// Filters compose (status + date range + returns-only), but not every
// combination is meaningful — this module is the single place that says so.

/**
 * Raised when a filter combination can never match real data, e.g. a date
 * range with `dateFrom` after `dateTo`, or `returnsOnly` paired with
 * `status: 'cancelled'` (cancelled orders never have an active return).
 */
export class FilterStateError extends Error {
  constructor(filters) {
    super(`invalid filter combination: ${describeFilters(filters)}`);
    this.name = 'FilterStateError';
    this.filters = filters;
  }
}

function describeFilters(filters) {
  try {
    return JSON.stringify(filters);
  } catch (e) {
    return String(filters);
  }
}

export const DEFAULT_FILTERS = {
  status: 'all', // all | fulfilled | processing | cancelled
  dateFrom: null,
  dateTo: null,
  returnsOnly: false,
};

/**
 * Throws FilterStateError if `filters` describes an impossible combination.
 * Returns the filters unchanged when valid (so callers can chain).
 */
export function validateFilters(filters) {
  const { status, dateFrom, dateTo, returnsOnly } = filters;

  if (dateFrom && dateTo && new Date(dateFrom).getTime() > new Date(dateTo).getTime()) {
    throw new FilterStateError(filters);
  }

  if (returnsOnly && status === 'cancelled') {
    throw new FilterStateError(filters);
  }

  return filters;
}

export function applyFilters(orders, returns, filters) {
  validateFilters(filters);

  let filteredOrders = orders;
  if (filters.status !== 'all') {
    filteredOrders = filteredOrders.filter((o) => o.status === filters.status);
  }
  if (filters.dateFrom) {
    const from = new Date(filters.dateFrom).getTime();
    filteredOrders = filteredOrders.filter((o) => new Date(o.placed_at).getTime() >= from);
  }
  if (filters.dateTo) {
    const to = new Date(filters.dateTo).getTime();
    filteredOrders = filteredOrders.filter((o) => new Date(o.placed_at).getTime() <= to);
  }

  if (filters.returnsOnly) {
    const orderIdsWithReturns = new Set(returns.map((r) => r.order_id));
    filteredOrders = filteredOrders.filter((o) => orderIdsWithReturns.has(o.id));
  }

  return filteredOrders;
}
