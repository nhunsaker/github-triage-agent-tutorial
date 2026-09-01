import React from 'react';

const STATUS_LABELS = {
  fulfilled: 'Fulfilled',
  processing: 'Processing',
  cancelled: 'Cancelled',
};

export default function OrdersPanel({ orders }) {
  return (
    <section className="panel">
      <h2>Orders</h2>
      <p className="panel-summary">{orders.length} orders in view</p>
      <table className="orders-table">
        <thead>
          <tr>
            <th>Order</th>
            <th>Customer</th>
            <th>SKU</th>
            <th>Status</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td>{o.id}</td>
              <td>{o.customer}</td>
              <td>{o.sku}</td>
              <td>
                <span className={`status-badge status-${o.status}`}>
                  {STATUS_LABELS[o.status] ?? o.status}
                </span>
              </td>
              <td>${o.total.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
