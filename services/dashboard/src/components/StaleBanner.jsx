import React from 'react';

// Wired straight to useOrders' staleness output — this is the visible half
// of DASH-001 (StaleDataWarning). The cause is often upstream (qr consumer
// lag, api publish failure); the banner just reports what the dashboard
// itself can see, which is "the numbers stopped moving."
export default function StaleBanner({ isStale, staleMinutes }) {
  if (!isStale) return null;

  return (
    <div className="stale-banner" role="status">
      Orders feed stale for {staleMinutes}m — showing cached data.
    </div>
  );
}
