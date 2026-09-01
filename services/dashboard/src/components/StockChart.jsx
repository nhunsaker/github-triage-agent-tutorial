import React from 'react';

// Inline-SVG bar chart, no charting library. Reads `data.stock.series`
// straight off the materialized snapshot — deliberately unguarded, because
// this is the file's failure mode: when the queue reader writes a
// malformed/partial snapshot (no `stock` key at all — a real shape the
// materializer can emit mid-write or after a schema-mismatch drop), the
// render crashes with the classic
//   TypeError: Cannot read properties of undefined (reading 'series')
// ChartRenderErrorBoundary below is what catches and surfaces it.

const BAR_HEIGHT = 22;
const BAR_GAP = 10;
const CHART_WIDTH = 420;
const LABEL_WIDTH = 160;

function StockBars({ data }) {
  // Intentionally unguarded: data.stock is expected to always be present
  // (the queue reader's contract), so this reads straight through. When
  // that contract is violated this line is exactly where it breaks.
  const bars = data.stock.series;

  const maxOnHand = Math.max(1, ...bars.map((b) => b.on_hand));

  return (
    <svg
      width={CHART_WIDTH}
      height={bars.length * (BAR_HEIGHT + BAR_GAP)}
      role="img"
      aria-label="Stock on hand by SKU"
    >
      {bars.map((bar, i) => {
        const y = i * (BAR_HEIGHT + BAR_GAP);
        const barWidth = ((CHART_WIDTH - LABEL_WIDTH) * bar.on_hand) / maxOnHand;
        return (
          <g key={bar.sku}>
            <text x={0} y={y + BAR_HEIGHT / 2 + 4} fontSize="11" fill="#333">
              {bar.name}
            </text>
            <rect
              x={LABEL_WIDTH}
              y={y}
              width={Math.max(2, barWidth)}
              height={BAR_HEIGHT}
              fill="#1a3e6f"
              rx="3"
            />
            <text
              x={LABEL_WIDTH + Math.max(2, barWidth) + 6}
              y={y + BAR_HEIGHT / 2 + 4}
              fontSize="11"
              fill="#1a3e6f"
            >
              {bar.on_hand}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/**
 * Raised (and re-thrown with this literal message) when StockBars fails to
 * find the expected `data.stock.series` shape. The boundary below catches
 * the raw TypeError React surfaces from the render and re-wraps it as this
 * named error so it's greppable and matches the catalog signature exactly.
 */
export class ChartRenderError extends Error {
  constructor(cause) {
    super("TypeError: Cannot read properties of undefined (reading 'series')");
    this.name = 'ChartRenderError';
    this.cause = cause;
  }
}

export class ChartRenderErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    const wrapped = new ChartRenderError(error);
    // eslint-disable-next-line no-console
    console.error(wrapped.message, { cause: error, info });
    this.setState({ error: wrapped });
  }

  render() {
    if (this.state.error) {
      return (
        <div className="chart-error" role="alert">
          <strong>Stock chart failed to render.</strong>
          <div className="chart-error-message">{this.state.error.message}</div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function StockChart({ data }) {
  return (
    <ChartRenderErrorBoundary>
      <StockBars data={data} />
    </ChartRenderErrorBoundary>
  );
}
