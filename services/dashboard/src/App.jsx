import React, { useMemo, useState } from 'react';
import { useOrders } from './hooks/useOrders.js';
import { DEFAULT_FILTERS, applyFilters, FilterStateError } from './state/filters.js';
import StockChart from './components/StockChart.jsx';
import OrdersPanel from './components/OrdersPanel.jsx';
import ReturnsPanel from './components/ReturnsPanel.jsx';
import StaleBanner from './components/StaleBanner.jsx';

import sampleData from './fixtures/materialized.sample.json';
import emptyStockData from './fixtures/materialized.emptystock.sample.json';

function useQueryParams() {
  return useMemo(() => new URLSearchParams(window.location.search), []);
}

export default function App() {
  const params = useQueryParams();
  const forceStale = params.get('stale') === '1';
  const useEmptyStock = params.get('emptyStock') === '1';

  const materialized = useEmptyStock ? emptyStockData : sampleData;

  const { orders, isStale, staleMinutes } = useOrders(materialized, { forceStale });

  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [filterError, setFilterError] = useState(null);

  const filteredOrders = useMemo(() => {
    try {
      const result = applyFilters(orders, materialized.returns ?? [], filters);
      setFilterError(null);
      return result;
    } catch (e) {
      if (e instanceof FilterStateError) {
        setFilterError(e);
        return orders;
      }
      throw e;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orders, materialized, filters]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Jane&apos;s Jeans — Store Ops</h1>
        <p className="app-subtitle">orders · stock · returns</p>
      </header>

      <StaleBanner isStale={isStale} staleMinutes={staleMinutes} />

      <section className="filter-bar">
        <label>
          Status:{' '}
          <select
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          >
            <option value="all">All</option>
            <option value="fulfilled">Fulfilled</option>
            <option value="processing">Processing</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={filters.returnsOnly}
            onChange={(e) => setFilters({ ...filters, returnsOnly: e.target.checked })}
          />{' '}
          Returns only
        </label>
        {filterError && (
          <span className="filter-error" role="alert">
            {filterError.message}
          </span>
        )}
      </section>

      <main className="panels">
        <OrdersPanel orders={filteredOrders} />
        <section className="panel">
          <h2>Stock on hand</h2>
          <StockChart data={materialized} />
        </section>
        <ReturnsPanel returns={materialized.returns ?? []} />
      </main>
    </div>
  );
}
