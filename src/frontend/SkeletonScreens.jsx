const range = (count) => Array.from({ length: count }, (_, index) => index)

const SkeletonLine = ({ className = "", width }) => (
  <span
    className={`skeleton-line skeleton-shimmer ${className}`}
    style={width ? { "--skeleton-width": width } : undefined}
  />
)

const SkeletonCell = ({ width }) => (
  <span className="skeleton-cell skeleton-shimmer" style={width ? { "--skeleton-width": width } : undefined} />
)

const SkeletonStatus = ({ label = "Loading content" }) => (
  <span className="skeleton-sr">{label}</span>
)

export const StockChartsSkeleton = () => (
  <section className="skeleton-screen stock-skeleton" role="status" aria-live="polite">
    <SkeletonStatus label="Loading stock charts" />
    <SkeletonLine className="skeleton-title-line" width="24rem" />
    <div className="charts-container">
      {range(2).map((item) => (
        <div className="chart-wrapper skeleton-chart-card" key={item}>
          <SkeletonLine width="11rem" />
          <div className="skeleton-chart-body skeleton-shimmer" />
          <div className="skeleton-chart-axis">
            {range(5).map((tick) => (
              <SkeletonCell key={tick} width="3rem" />
            ))}
          </div>
        </div>
      ))}
    </div>
  </section>
)

export const MetricCardsSkeleton = ({ cards = 5, label = "Loading metrics" }) => (
  <section className="metrics-container skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label={label} />
    <div className="text-center mb-8">
      <SkeletonLine className="skeleton-title-line" width="18rem" />
    </div>
    <div className="metrics-grid">
      {range(cards).map((card) => (
        <div className="metric-card skeleton-metric-card" key={card}>
          <SkeletonLine width="7rem" />
          <SkeletonLine className="skeleton-value-line" width="5rem" />
        </div>
      ))}
    </div>
  </section>
)

export const ResultCardsSkeleton = ({ cards = 4, label = "Loading results" }) => (
  <section className="skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label={label} />
    <div className="grid-auto">
      {range(cards).map((card) => (
        <div className="stat-card skeleton-stat-card" key={card}>
          <SkeletonLine width="8rem" />
          <SkeletonLine className="skeleton-value-line" width={card === 0 ? "11rem" : "6rem"} />
          <SkeletonLine width="9rem" />
        </div>
      ))}
    </div>
  </section>
)

export const FinancialTableSkeleton = ({ rows = 8, columns = 5 }) => (
  <div className="financial-table-container skeleton-table-wrapper" role="status" aria-live="polite">
    <SkeletonStatus label="Loading financial table" />
    <table className="financial-table skeleton-table">
      <thead>
        <tr>
          {range(columns).map((column) => (
            <th key={column}>
              <SkeletonCell width={column === 0 ? "9rem" : "5rem"} />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {range(rows).map((row) => (
          <tr key={row}>
            {range(columns).map((column) => (
              <td key={column}>
                <SkeletonCell width={column === 0 ? "12rem" : `${4 + (row + column) % 3}rem`} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

export const GenericTableSkeleton = ({ rows = 6, columns = 6, label = "Loading table" }) => (
  <div className="table-wrapper skeleton-table-wrapper" role="status" aria-live="polite">
    <SkeletonStatus label={label} />
    <table className="premium-table skeleton-table">
      <thead>
        <tr>
          {range(columns).map((column) => (
            <th key={column}>
              <SkeletonCell width={column === 1 ? "8rem" : "5rem"} />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {range(rows).map((row) => (
          <tr key={row}>
            {range(columns).map((column) => (
              <td key={column}>
                <SkeletonCell width={column === 1 ? "11rem" : `${4 + (row + column) % 4}rem`} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

export const OptimizerSkeleton = () => (
  <section className="optimizer-results-container skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label="Loading optimization results" />
    <SkeletonLine className="skeleton-title-line" width="16rem" />
    <div className="optimizer-results-grid">
      {range(3).map((card) => (
        <div className="optimizer-result-card skeleton-metric-card" key={card}>
          <SkeletonLine width="8rem" />
          <SkeletonLine className="skeleton-value-line" width="5rem" />
        </div>
      ))}
    </div>
    <div className="optimizer-weights-card">
      <SkeletonLine width="10rem" />
      <ul className="optimizer-weights-list skeleton-list">
        {range(8).map((item) => (
          <li key={item}>
            <SkeletonCell width="5rem" />
            <SkeletonCell width="4rem" />
          </li>
        ))}
      </ul>
    </div>
  </section>
)

export const BenchmarkSkeleton = () => (
  <section className="benchmark-results skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label="Loading benchmark results" />
    <SkeletonLine className="skeleton-title-line" width="14rem" />
    <div className="charts-container">
      <div className="chart-wrapper skeleton-chart-card">
        <SkeletonLine width="12rem" />
        <div className="skeleton-chart-body skeleton-shimmer" />
      </div>
    </div>
    <div className="benchmark-table-container">
      <GenericTableSkeleton rows={3} columns={5} label="Loading benchmark table" />
    </div>
  </section>
)

export const ManagerSkeleton = () => (
  <section className="manager-results skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label="Loading rebalancing results" />
    <SkeletonLine className="skeleton-title-line" width="16rem" />
    <div className="manager-summary-grid">
      <div className="manager-summary-card manager-summary-card-wide">
        <SkeletonLine width="11rem" />
        <SkeletonLine className="skeleton-value-line" width="9rem" />
      </div>
      {range(3).map((card) => (
        <div className="manager-summary-card manager-summary-metric-card" key={card}>
          <SkeletonLine width="8rem" />
          <SkeletonLine className="skeleton-value-line" width="5rem" />
        </div>
      ))}
    </div>
    <div className="manager-charts-row">
      {range(2).map((chart) => (
        <div className="chart-wrapper skeleton-chart-card" key={chart}>
          <SkeletonLine width="10rem" />
          <div className="skeleton-pie skeleton-shimmer" />
        </div>
      ))}
    </div>
    <div className="manager-order-section">
      <SkeletonLine className="skeleton-title-line" width="8rem" />
      <GenericTableSkeleton rows={5} columns={4} label="Loading order table" />
    </div>
  </section>
)

export const ScreenerSkeleton = () => (
  <section className="results-section fade-in skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label="Loading screener results" />
    <div className="results-header">
      <SkeletonLine width="8rem" />
      <SkeletonLine width="7rem" />
    </div>
    <GenericTableSkeleton rows={7} columns={8} label="Loading screener table" />
  </section>
)
