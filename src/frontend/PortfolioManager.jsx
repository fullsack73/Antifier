"use client"

import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"
import Plot from "react-plotly.js"

const PortfolioManager = () => {
  const { t } = useTranslation()

  // Holdings state: array of { ticker, quantity }
  const [holdings, setHoldings] = useState([{ ticker: "", quantity: "" }])
  const [cashInjection, setCashInjection] = useState("")

  // Configuration mirrored from Optimizer
  const [forecastMethod, setForecastMethod] = useState("LIGHTWEIGHT")
  const [optimizationMethod, setOptimizationMethod] = useState("BL")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [riskFreeRate, setRiskFreeRate] = useState("2")

  // Results state
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // CSV upload
  const csvFileInputRef = useRef(null)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadFileName, setUploadFileName] = useState("")
  const [uploadError, setUploadError] = useState(null)

  // --- Holdings Management ---
  const addHolding = () => {
    setHoldings([...holdings, { ticker: "", quantity: "" }])
  }

  const removeHolding = (index) => {
    setHoldings(holdings.filter((_, i) => i !== index))
  }

  const updateHolding = (index, field, value) => {
    const updated = [...holdings]
    updated[index] = { ...updated[index], [field]: value }
    setHoldings(updated)
  }

  // --- CSV Upload for Holdings ---
  const handleCsvUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return

    setUploadError(null)
    setUploadFileName(file.name)

    if (!file.name.toLowerCase().endsWith(".csv")) {
      setUploadError("Only .csv files are accepted.")
      e.target.value = ""
      return
    }

    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target.result
      const lines = text.split(/[\r\n]+/).filter((l) => l.trim())

      // Skip header line if it looks like one
      const dataLines = lines.filter(
        (l) => !/^(symbol|ticker|name|company|quantity)/i.test(l.trim())
      )

      const parsed = dataLines
        .map((line) => {
          const parts = line.split(",").map((p) => p.trim())
          if (parts.length >= 2 && /^[A-Z0-9.\-^]+$/i.test(parts[0])) {
            const qty = Number.parseFloat(parts[1])
            if (!isNaN(qty) && qty > 0) {
              return { ticker: parts[0].toUpperCase(), quantity: String(qty) }
            }
          }
          return null
        })
        .filter(Boolean)

      if (parsed.length === 0) {
        setUploadError("No valid holdings found. Format: TICKER,QUANTITY per line.")
      } else {
        setHoldings(parsed)
        setShowUploadModal(false)
      }
    }
    reader.onerror = () => setUploadError("Failed to read file.")
    reader.readAsText(file)
    e.target.value = ""
  }

  // --- Build holdings dict from form ---
  const buildHoldingsDict = () => {
    const dict = {}
    for (const h of holdings) {
      const ticker = h.ticker.trim().toUpperCase()
      const qty = Number.parseFloat(h.quantity)
      if (ticker && !isNaN(qty) && qty > 0) {
        dict[ticker] = (dict[ticker] || 0) + qty
      }
    }
    return dict
  }

  // --- Submit ---
  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResults(null)

    const holdingsDict = buildHoldingsDict()
    if (Object.keys(holdingsDict).length === 0) {
      setError(t("manager.noHoldings", "Please add at least one holding."))
      setLoading(false)
      return
    }

    try {
      const payload = {
        current_holdings: holdingsDict,
        cash_injection: Number.parseFloat(cashInjection) || 0,
        start_date: startDate,
        end_date: endDate,
        risk_free_rate: Number.parseFloat(riskFreeRate) / 100,
        forecast_method: forecastMethod,
        optimization_method: optimizationMethod,
      }

      const response = await axios.post(
        "http://127.0.0.1:5000/api/manage-portfolio",
        payload
      )
      setResults(response.data)
    } catch (err) {
      if (err.response && err.response.data) {
        setError(err.response.data.error || "An error occurred")
      } else {
        setError(err.message || "An error occurred")
      }
    } finally {
      setLoading(false)
    }
  }

  // --- Chart helpers ---
  const buildCurrentPieData = () => {
    if (!results || !results.prices) return null
    const holdingsDict = buildHoldingsDict()
    const labels = []
    const values = []
    for (const [ticker, qty] of Object.entries(holdingsDict)) {
      const price = results.prices[ticker] || 0
      labels.push(ticker)
      values.push(qty * price)
    }
    return { labels, values }
  }

  const buildTargetPieData = () => {
    if (!results || !results.weights || !results.prices) return null
    const holdingsDict = buildHoldingsDict()
    const totalCurrentValue = Object.entries(holdingsDict).reduce(
      (sum, [ticker, qty]) => sum + qty * (results.prices[ticker] || 0),
      0
    )
    const totalTarget =
      totalCurrentValue + (Number.parseFloat(cashInjection) || 0)

    const labels = []
    const values = []
    for (const [ticker, weight] of Object.entries(results.weights)) {
      if (weight > 0.0001) {
        labels.push(ticker)
        values.push(weight * totalTarget)
      }
    }
    return { labels, values }
  }

  const chartLayout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#e5e7eb", family: "IBM Plex Sans, Pretendard, sans-serif" },
    margin: { t: 40, b: 20, l: 20, r: 20 },
    showlegend: true,
    legend: { font: { size: 11 } },
    height: 350,
  }

  const currentPie = buildCurrentPieData()
  const targetPie = buildTargetPieData()

  return (
    <div className="manager-container">
      <h2 className="page-header">{t("manager.title", "Portfolio Manager")}</h2>

      {/* Actions row */}
      <div className="optimizer-actions-row" style={{ marginBottom: "1rem" }}>
        <button
          className="optimizer-secondary-button"
          type="button"
          onClick={() => setShowUploadModal(true)}
        >
          {t("manager.uploadCsv", "Upload Holdings CSV")}
        </button>
      </div>

      {/* CSV Upload Modal */}
      {showUploadModal && (
        <div
          className="optimizer-modal-overlay"
          onClick={() => setShowUploadModal(false)}
        >
          <div
            className="optimizer-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="optimizer-modal-header">
              <h3 className="optimizer-modal-title">
                {t("manager.uploadHoldings", "Upload Holdings")}
              </h3>
              <button
                type="button"
                className="optimizer-modal-close"
                onClick={() => setShowUploadModal(false)}
              >
                ×
              </button>
            </div>
            <div className="optimizer-modal-body">
              <p
                style={{
                  fontSize: "0.85rem",
                  color: "var(--color-text-muted)",
                  marginBottom: "var(--spacing-md)",
                }}
              >
                {t(
                  "manager.csvInstructions",
                  "Upload a .csv file with TICKER,QUANTITY per line (e.g., AAPL,10)."
                )}
              </p>
              <button
                type="button"
                className="optimizer-secondary-button"
                onClick={() => csvFileInputRef.current?.click()}
                style={{ width: "100%", marginBottom: "var(--spacing-md)" }}
              >
                {uploadFileName
                  ? t("optimizer.changeFile", "Change File")
                  : t("manager.chooseCsvFile", "Choose CSV File")}
              </button>
              <input
                type="file"
                accept=".csv"
                ref={csvFileInputRef}
                style={{ display: "none" }}
                onChange={handleCsvUpload}
              />
              {uploadError && (
                <div
                  style={{
                    fontSize: "0.85rem",
                    color: "var(--color-danger)",
                    marginBottom: "var(--spacing-md)",
                  }}
                >
                  {uploadError}
                </div>
              )}
            </div>
            <div className="optimizer-modal-footer">
              <button
                type="button"
                className="optimizer-secondary-button"
                onClick={() => setShowUploadModal(false)}
              >
                {t("common.close", "Close")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Form */}
      <form onSubmit={handleSubmit} className="optimizer-form">
        {/* Holdings Input */}
        <div className="manager-holdings-section">
          <h3 className="manager-section-title">
            {t("manager.currentHoldings", "Current Holdings")}
          </h3>
          <div className="manager-holdings-list">
            {holdings.map((h, i) => (
              <div key={i} className="manager-holding-row">
                <input
                  className="optimizer-input"
                  type="text"
                  placeholder={t("manager.tickerPlaceholder", "e.g., AAPL")}
                  value={h.ticker}
                  onChange={(e) =>
                    updateHolding(i, "ticker", e.target.value.toUpperCase())
                  }
                  style={{ textTransform: "uppercase" }}
                  required
                />
                <input
                  className="optimizer-input"
                  type="number"
                  placeholder={t("manager.quantityPlaceholder", "e.g., 10")}
                  value={h.quantity}
                  onChange={(e) => updateHolding(i, "quantity", e.target.value)}
                  step="any"
                  min="0"
                  required
                />
                {holdings.length > 1 && (
                  <button
                    type="button"
                    className="remove-filter-btn"
                    onClick={() => removeHolding(i)}
                    aria-label="Remove holding"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
          <button
            type="button"
            className="optimizer-secondary-button"
            onClick={addHolding}
            style={{ marginTop: "var(--spacing-sm)" }}
          >
            {t("manager.addHolding", "+ Add Holding")}
          </button>
        </div>

        {/* Cash injection */}
        <div className="optimizer-form-group">
          <label htmlFor="cashInjection">
            {t("manager.cashInjection", "Cash Injection ($)")}
          </label>
          <input
            id="cashInjection"
            className="optimizer-input"
            type="number"
            value={cashInjection}
            onChange={(e) => setCashInjection(e.target.value)}
            placeholder={t("manager.cashPlaceholder", "e.g., 5000")}
            step="any"
            min="0"
          />
        </div>

        {/* Configuration grid */}
        <div className="optimizer-form-grid">
          <div className="optimizer-form-group">
            <label htmlFor="mgr-forecastMethod">
              {t("optimizer.forecastMethod", "Forecast Method")}
            </label>
            <select
              id="mgr-forecastMethod"
              className="optimizer-select"
              value={forecastMethod}
              onChange={(e) => setForecastMethod(e.target.value)}
            >
              <option value="LIGHTWEIGHT">
                {t("optimizer.lightweight", "Lightweight Prediction")}
              </option>
              <option value="DEEP_LEARNING">
                {t("optimizer.ensemble", "Deep Learning Ensemble")}
              </option>
            </select>
          </div>

          <div className="optimizer-form-group">
            <label htmlFor="mgr-optimizationMethod">
              {t("optimizer.optimizationMethod", "Optimization Method")}
            </label>
            <select
              id="mgr-optimizationMethod"
              className="optimizer-select"
              value={optimizationMethod}
              onChange={(e) => setOptimizationMethod(e.target.value)}
            >
              <option value="BL">
                {t("optimizer.bl", "Black-Litterman")}
              </option>
              <option value="MPT">
                {t("optimizer.mpt", "Mean-Variance (MPT)")}
              </option>
            </select>
          </div>

          <div className="optimizer-form-group">
            <label htmlFor="mgr-startDate">
              {t("optimizer.startDate", "Start Date")}
            </label>
            <input
              id="mgr-startDate"
              className="optimizer-input"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
          </div>

          <div className="optimizer-form-group">
            <label htmlFor="mgr-endDate">
              {t("optimizer.endDate", "End Date")}
            </label>
            <input
              id="mgr-endDate"
              className="optimizer-input"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              required
            />
          </div>

          <div className="optimizer-form-group">
            <label htmlFor="mgr-riskFreeRate">
              {t("optimizer.riskFreeRate", "Risk-Free Rate (%)")}
            </label>
            <input
              id="mgr-riskFreeRate"
              className="optimizer-input"
              type="number"
              value={riskFreeRate}
              onChange={(e) => setRiskFreeRate(e.target.value)}
              placeholder="e.g., 2"
              required
            />
          </div>

          <button
            type="submit"
            className="optimizer-submit-button"
            disabled={loading}
          >
            {loading
              ? t("common.loading", "Loading...")
              : t("manager.rebalance", "Rebalance Portfolio")}
          </button>
        </div>
      </form>

      {/* Error */}
      {error && (
        <div className="optimizer-error">
          <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
            {t("common.error", "Error")}
          </div>
          <div>{error}</div>
        </div>
      )}

      {/* Results */}
      {results && (
        <div className="manager-results">
          <h3 className="manager-results-title">
            {t("manager.resultsTitle", "Rebalancing Results")}
          </h3>

          {/* Pie Charts */}
          <div className="manager-charts-row">
            {currentPie && (
              <div className="chart-wrapper">
                <h4 className="manager-chart-title">
                  {t("manager.currentAllocation", "Current Allocation")}
                </h4>
                <Plot
                  data={[
                    {
                      type: "pie",
                      labels: currentPie.labels,
                      values: currentPie.values,
                      hole: 0.4,
                      textinfo: "label+percent",
                      textfont: { size: 11, color: "#e5e7eb" },
                      marker: {
                        colors: [
                          "#3b82f6", "#06b6d4", "#10b981", "#f59e0b",
                          "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
                          "#f97316", "#6366f1",
                        ],
                      },
                    },
                  ]}
                  layout={{
                    ...chartLayout,
                    title: { text: t("manager.currentAllocation", "Current Allocation"), font: { color: "#e5e7eb", size: 14 } },
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: "100%" }}
                />
              </div>
            )}
            {targetPie && (
              <div className="chart-wrapper">
                <h4 className="manager-chart-title">
                  {t("manager.targetAllocation", "Target Allocation")}
                </h4>
                <Plot
                  data={[
                    {
                      type: "pie",
                      labels: targetPie.labels,
                      values: targetPie.values,
                      hole: 0.4,
                      textinfo: "label+percent",
                      textfont: { size: 11, color: "#e5e7eb" },
                      marker: {
                        colors: [
                          "#3b82f6", "#06b6d4", "#10b981", "#f59e0b",
                          "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
                          "#f97316", "#6366f1",
                        ],
                      },
                    },
                  ]}
                  layout={{
                    ...chartLayout,
                    title: { text: t("manager.targetAllocation", "Target Allocation"), font: { color: "#e5e7eb", size: 14 } },
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: "100%" }}
                />
              </div>
            )}
          </div>

          {/* Metrics */}
          {results.expected_return !== undefined && (
            <div className="optimizer-results-grid" style={{ marginTop: "var(--spacing-xl)" }}>
              <div className="optimizer-result-card">
                <h4>{t("optimizer.return", "Expected Return")}</h4>
                <p>{(results.expected_return * 100).toFixed(2)}%</p>
              </div>
              <div className="optimizer-result-card">
                <h4>{t("optimizer.risk", "Risk (Std. Dev)")}</h4>
                <p>{(results.volatility * 100).toFixed(2)}%</p>
              </div>
              <div className="optimizer-result-card">
                <h4>{t("optimizer.sharpeRatio", "Sharpe Ratio")}</h4>
                <p>{results.sharpe_ratio?.toFixed(2) ?? "N/A"}</p>
              </div>
            </div>
          )}

          {/* Buy List */}
          {results.buy_list && Object.keys(results.buy_list).length > 0 && (
            <div className="manager-order-section">
              <h4 className="manager-order-title manager-buy-title">
                {t("manager.buyList", "Buy List")}
              </h4>
              <table className="allocation-table">
                <thead>
                  <tr>
                    <th>{t("optimizer.ticker", "Ticker")}</th>
                    <th>{t("optimizer.shares", "Shares")}</th>
                    <th>{t("optimizer.price", "Price")}</th>
                    <th>{t("optimizer.investmentAmount", "Value")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(results.buy_list).map(([ticker, data]) => (
                    <tr key={ticker}>
                      <td className="ticker-cell">{ticker}</td>
                      <td className="number-cell">
                        {data.quantity?.toFixed(4)}
                      </td>
                      <td className="number-cell">
                        ${data.price?.toFixed(2)}
                      </td>
                      <td className="number-cell positive">
                        +${data.value?.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Sell List */}
          {results.sell_list && Object.keys(results.sell_list).length > 0 && (
            <div className="manager-order-section">
              <h4 className="manager-order-title manager-sell-title">
                {t("manager.sellList", "Sell List")}
              </h4>
              <table className="allocation-table">
                <thead>
                  <tr>
                    <th>{t("optimizer.ticker", "Ticker")}</th>
                    <th>{t("optimizer.shares", "Shares")}</th>
                    <th>{t("optimizer.price", "Price")}</th>
                    <th>{t("optimizer.investmentAmount", "Value")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(results.sell_list).map(([ticker, data]) => (
                    <tr key={ticker}>
                      <td className="ticker-cell">{ticker}</td>
                      <td className="number-cell">
                        {data.quantity?.toFixed(4)}
                      </td>
                      <td className="number-cell">
                        ${data.price?.toFixed(2)}
                      </td>
                      <td className="number-cell negative">
                        -${data.value?.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Target Weights */}
          {results.weights && (
            <div className="optimizer-weights-card" style={{ marginTop: "var(--spacing-xl)" }}>
              <h4>{t("optimizer.weights", "Target Weights")}</h4>
              <ul className="optimizer-weights-list">
                {Object.entries(results.weights)
                  .filter(([, w]) => w > 0.0001)
                  .sort(([, a], [, b]) => b - a)
                  .map(([ticker, weight]) => (
                    <li key={ticker}>
                      <span>{ticker}</span>
                      <strong>{(weight * 100).toFixed(2)}%</strong>
                    </li>
                  ))}
              </ul>
            </div>
          )}

          {/* Total Target Value */}
          {results.total_target_value && (
            <div
              className="manager-summary-card"
              style={{ marginTop: "var(--spacing-xl)" }}
            >
              <span className="manager-summary-label">
                {t("manager.totalTargetValue", "Total Target Value")}
              </span>
              <span className="manager-summary-value">
                ${results.total_target_value.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default PortfolioManager
