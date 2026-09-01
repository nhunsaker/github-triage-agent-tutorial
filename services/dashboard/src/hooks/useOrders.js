import { useEffect, useMemo, useState } from 'react';

// Threshold above which the materialized orders feed is considered stale.
// The queue reader (services/qr) writes data/materialized/orders.json on
// every consumed event; if that write stops (consumer lag, DLQ backup,
// crash) the dashboard keeps showing the last-known snapshot and warns.
export const STALE_THRESHOLD_MINUTES = 5;

/**
 * Raised when the materialized orders feed is older than
 * STALE_THRESHOLD_MINUTES. This is the dashboard's half of the classic
 * "order counts frozen since 2pm" ambiguous case — the real fault is often
 * upstream (services/qr consumer lag or services/api publish failure), but
 * this is where the symptom surfaces to the store-ops user.
 */
export class StaleDataWarning extends Error {
  constructor(minutes) {
    super(`orders feed stale for ${minutes}m, showing cached data`);
    this.name = 'StaleDataWarning';
    this.minutes = minutes;
  }
}

function minutesSince(isoTimestamp, now) {
  const then = new Date(isoTimestamp).getTime();
  return Math.floor((now - then) / 60000);
}

/**
 * Loads the materialized snapshot (fixture by default) and derives orders +
 * a staleness flag. `?stale=1` in the URL forces the stale path for demo
 * purposes without needing to wait out a real clock.
 *
 * `now` is injectable for tests; defaults to Date.now().
 */
export function useOrders(materialized, { now = Date.now(), forceStale = false } = {}) {
  const [warning, setWarning] = useState(null);

  const staleness = useMemo(() => {
    if (!materialized || !materialized.generated_at) {
      return { isStale: false, minutes: 0 };
    }
    const minutes = forceStale
      ? STALE_THRESHOLD_MINUTES + 1
      : minutesSince(materialized.generated_at, now);
    return { isStale: minutes > STALE_THRESHOLD_MINUTES, minutes };
  }, [materialized, now, forceStale]);

  useEffect(() => {
    if (staleness.isStale) {
      const err = new StaleDataWarning(staleness.minutes);
      // eslint-disable-next-line no-console
      console.warn(err.message, err);
      setWarning(err);
    } else {
      setWarning(null);
    }
  }, [staleness.isStale, staleness.minutes]);

  const orders = materialized?.orders ?? [];

  return {
    orders,
    isStale: staleness.isStale,
    staleMinutes: staleness.minutes,
    warning,
  };
}
