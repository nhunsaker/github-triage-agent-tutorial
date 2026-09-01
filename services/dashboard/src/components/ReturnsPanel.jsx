import React from 'react';

const STATE_LABELS = {
  requested: 'Requested',
  approved: 'Approved',
  completed: 'Completed',
};

export default function ReturnsPanel({ returns }) {
  return (
    <section className="panel">
      <h2>Returns</h2>
      <p className="panel-summary">{returns.length} returns in view</p>
      <ul className="returns-list">
        {returns.map((r) => (
          <li key={r.id}>
            <span className={`state-badge state-${r.state}`}>{STATE_LABELS[r.state] ?? r.state}</span>
            <span className="returns-detail">
              {r.id} — order {r.order_id} — {r.sku} — {r.reason}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
