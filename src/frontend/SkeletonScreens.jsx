import { useTranslation } from "react-i18next"

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

const SkeletonStatus = ({ label, i18nKey = "skeleton.loadingContent" }) => {
  const { t } = useTranslation()
  return <span className="skeleton-sr">{label || t(i18nKey)}</span>
}

export const StockChartsSkeleton = () => (
  <section className="skeleton-screen stock-skeleton" role="status" aria-live="polite">
    <SkeletonStatus i18nKey="skeleton.loadingStockCharts" />
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

export const MetricCardsSkeleton = ({ cards = 5, label }) => (
  <section className="metrics-container skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label={label} i18nKey="skeleton.loadingMetrics" />
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

export const ResultCardsSkeleton = ({ cards = 4, label }) => (
  <section className="skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus label={label} i18nKey="skeleton.loadingResults" />
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
    <SkeletonStatus i18nKey="skeleton.loadingFinancialTable" />
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

export const GenericTableSkeleton = ({ rows = 6, columns = 6, label, i18nKey = "skeleton.loadingTable" }) => (
  <div className="table-wrapper skeleton-table-wrapper" role="status" aria-live="polite">
    <SkeletonStatus label={label} i18nKey={i18nKey} />
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
    <SkeletonStatus i18nKey="skeleton.loadingOptimizationResults" />
    <div className="optimizer-results-header">
      <div>
        <SkeletonLine width="7rem" />
        <SkeletonLine className="skeleton-title-line" width="16rem" />
      </div>
    </div>
    <div className="optimizer-result-summary optimizer-skeleton-summary">
      <div className="optimizer-result-primary">
        <SkeletonLine width="8rem" />
        <SkeletonLine className="skeleton-value-line" width="13rem" />
        <SkeletonLine width="17rem" />
      </div>
      <div className="optimizer-result-secondary">
        {range(2).map((card) => (
          <div key={card}>
            <SkeletonLine width="7rem" />
            <SkeletonLine className="skeleton-value-line" width="5rem" />
            <SkeletonLine width="9rem" />
          </div>
        ))}
      </div>
    </div>
    <div className="optimizer-weights-card">
      <div className="optimizer-weights-header">
        <div>
          <SkeletonLine width="6rem" />
          <SkeletonLine className="skeleton-title-line" width="10rem" />
        </div>
      </div>
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
    <SkeletonStatus i18nKey="skeleton.loadingBenchmarkResults" />
    <SkeletonLine className="skeleton-title-line" width="14rem" />
    <div className="charts-container">
      <div className="chart-wrapper skeleton-chart-card">
        <SkeletonLine width="12rem" />
        <div className="skeleton-chart-body skeleton-shimmer" />
      </div>
    </div>
    <div className="benchmark-table-container">
      <GenericTableSkeleton rows={3} columns={5} i18nKey="skeleton.loadingBenchmarkTable" />
    </div>
  </section>
)

export const ManagerSkeleton = () => (
  <section className="manager-results skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus i18nKey="skeleton.loadingRebalancingResults" />
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
      <GenericTableSkeleton rows={5} columns={4} i18nKey="skeleton.loadingOrderTable" />
    </div>
  </section>
)

export const ScreenerSkeleton = () => (
  <section className="results-section fade-in skeleton-screen" role="status" aria-live="polite">
    <SkeletonStatus i18nKey="skeleton.loadingScreenerResults" />
    <div className="results-header">
      <SkeletonLine width="8rem" />
      <SkeletonLine width="7rem" />
    </div>
    <GenericTableSkeleton rows={7} columns={8} i18nKey="skeleton.loadingScreenerTable" />
  </section>
)
