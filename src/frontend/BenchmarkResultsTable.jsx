import { useTranslation } from "react-i18next"

function BenchmarkResultsTable({ summary }) {
  const { t } = useTranslation()

  const formatCurrency = (value) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  }

  const formatPercent = (value) => {
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
  }

  const getColorClass = (value) => {
    return value >= 0 ? "positive" : "negative"
  }

  const rows = [
    {
      name: t("benchmark.portfolio"),
      data: summary.portfolio,
    },
    {
      name: t("benchmark.sp500"),
      data: summary.sp500_benchmark,
    },
    {
      name: t("benchmark.riskFree"),
      data: summary.risk_free_asset,
    },
  ]

  const sp500Delta = summary.portfolio.return_pct - summary.sp500_benchmark.return_pct
  const riskFreeDelta = summary.portfolio.return_pct - summary.risk_free_asset.return_pct

  return (
    <section className="benchmark-summary-panel" aria-labelledby="benchmark-summary-title">
      <div className="benchmark-summary-heading">
        <div>
          <h3 id="benchmark-summary-title">{t("benchmark.comparison")}</h3>
          <p>{t("benchmark.comparisonDescription")}</p>
        </div>
        <div className="benchmark-delta-grid">
          <div>
            <span>{t("benchmark.vssp500")}</span>
            <strong className={getColorClass(sp500Delta)}>{formatPercent(sp500Delta)}</strong>
          </div>
          <div>
            <span>{t("benchmark.vsRiskFree")}</span>
            <strong className={getColorClass(riskFreeDelta)}>{formatPercent(riskFreeDelta)}</strong>
          </div>
        </div>
      </div>

      <div className="benchmark-table-scroll">
        <table className="benchmark-table">
          <caption>{t("benchmark.tableCaption")}</caption>
          <thead>
            <tr>
              <th>{t("benchmark.investmentType")}</th>
              <th>{t("benchmark.initialValue")}</th>
              <th>{t("benchmark.finalValue")}</th>
              <th>{t("benchmark.profitLoss")}</th>
              <th>{t("benchmark.returnPercent")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <th scope="row" className="benchmark-name">
                  {row.name}
                </th>
                <td data-label={t("benchmark.initialValue")}>
                  {formatCurrency(row.data.initial_value)}
                </td>
                <td data-label={t("benchmark.finalValue")}>
                  {formatCurrency(row.data.final_value)}
                </td>
                <td
                  data-label={t("benchmark.profitLoss")}
                  className={getColorClass(row.data.profit_loss)}
                >
                  {formatCurrency(row.data.profit_loss)}
                </td>
                <td
                  data-label={t("benchmark.returnPercent")}
                  className={getColorClass(row.data.return_pct)}
                >
                  {formatPercent(row.data.return_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default BenchmarkResultsTable
