"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"
import Plot from "./LazyPlot.jsx"
import {
  buildExportBaseName,
  buildPortfolioExportPayload,
  buildTargetHoldingsCsv,
  downloadBlob,
} from "./portfolioManagerExports"
import { fetchSecurityNames, formatSecurityDisplay, getSecurityDisplayName } from "./securityDisplay"
import { apiUrl } from "./apiClient.js"
import { ManagerSkeleton } from "./SkeletonScreens.jsx"

const PORTFOLIO_MANAGER_STORAGE_KEY = "portfolio-manager-saved-input-v1"
const DEFAULT_HOLDINGS = [{ ticker: "", quantity: "" }]

const PortfolioManager = () => {
  const { t } = useTranslation()

  // Holdings state: array of { ticker, quantity }
  const [holdings, setHoldings] = useState(DEFAULT_HOLDINGS)
  const [cashInjection, setCashInjection] = useState("")

  // Configuration mirrored from Optimizer
  const [forecastMethod, setForecastMethod] = useState("LIGHTWEIGHT")
  const [optimizationMethod, setOptimizationMethod] = useState("BL")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [riskFreeRate, setRiskFreeRate] = useState("2")

  const [forecastHorizon, setForecastHorizon] = useState("63")
  const [minHistory, setMinHistory] = useState("504")
  const [blTau, setBlTau] = useState("0.05")
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [tickerGroup, setTickerGroup] = useState("CURRENT_HOLDINGS")
  const [customTickers, setCustomTickers] = useState([])
  const [allowFractional, setAllowFractional] = useState(false)
  const [fractionalOverrides, setFractionalOverrides] = useState({})
  const [orderDisplayMode, setOrderDisplayMode] = useState("all") // 'all' | 'shares' | 'value'
  const [securityDisplayMode, setSecurityDisplayMode] = useState("ticker")
  const [assetNameOverrides, setAssetNameOverrides] = useState({})
  const [hasSavedPortfolio, setHasSavedPortfolio] = useState(false)
  const [savedPortfolioStatus, setSavedPortfolioStatus] = useState("")

  // Results state
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // CSV upload
  const csvFileInputRef = useRef(null)
  const spaceCsvFileInputRef = useRef(null)
  const resultsPrintRef = useRef(null)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showSpaceUploadModal, setShowSpaceUploadModal] = useState(false)
  const [uploadFileName, setUploadFileName] = useState("")
  const [spaceUploadFileName, setSpaceUploadFileName] = useState("")
  const [uploadError, setUploadError] = useState(null)
  const [spaceUploadError, setSpaceUploadError] = useState(null)

  useEffect(() => {
    try {
      setHasSavedPortfolio(Boolean(window.localStorage.getItem(PORTFOLIO_MANAGER_STORAGE_KEY)))
    } catch {
      setHasSavedPortfolio(false)
    }
  }, [])

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

  const buildPortfolioSnapshot = () => ({
    holdings,
    cashInjection,
    forecastMethod,
    optimizationMethod,
    startDate,
    endDate,
    riskFreeRate,
    forecastHorizon,
    minHistory,
    blTau,
    tickerGroup,
    customTickers,
    spaceUploadFileName,
    allowFractional,
    fractionalOverrides,
    savedAt: new Date().toISOString(),
  })

  const handleSavePortfolio = () => {
    try {
      window.localStorage.setItem(
        PORTFOLIO_MANAGER_STORAGE_KEY,
        JSON.stringify(buildPortfolioSnapshot())
      )
      setHasSavedPortfolio(true)
      setSavedPortfolioStatus(t("manager.savedPortfolio", "Portfolio saved in this browser."))
    } catch {
      setSavedPortfolioStatus(
        t("manager.savePortfolioError", "Could not save portfolio in this browser.")
      )
    }
  }

  const handleLoadPortfolio = () => {
    try {
      const savedPortfolio = window.localStorage.getItem(PORTFOLIO_MANAGER_STORAGE_KEY)
      if (!savedPortfolio) {
        setHasSavedPortfolio(false)
        setSavedPortfolioStatus(t("manager.noSavedPortfolio", "No saved portfolio found."))
        return
      }

      const parsed = JSON.parse(savedPortfolio)
      if (!Array.isArray(parsed.holdings)) {
        throw new Error("Invalid saved portfolio")
      }

      const savedHoldings = parsed.holdings
        .map((holding) => ({
          ticker: String(holding?.ticker || "").toUpperCase(),
          quantity: String(holding?.quantity || ""),
        }))
        .filter((holding) => holding.ticker || holding.quantity)

      setHoldings(savedHoldings.length > 0 ? savedHoldings : DEFAULT_HOLDINGS)
      setCashInjection(String(parsed.cashInjection || ""))
      setForecastMethod(parsed.forecastMethod || "LIGHTWEIGHT")
      setOptimizationMethod(parsed.optimizationMethod || "BL")
      setStartDate(String(parsed.startDate || ""))
      setEndDate(String(parsed.endDate || ""))
      setRiskFreeRate(String(parsed.riskFreeRate || "2"))
      setForecastHorizon(String(parsed.forecastHorizon || "63"))
      setMinHistory(String(parsed.minHistory || "504"))
      setBlTau(String(parsed.blTau || "0.05"))
      setTickerGroup(parsed.tickerGroup || "CURRENT_HOLDINGS")
      setCustomTickers(Array.isArray(parsed.customTickers) ? parsed.customTickers : [])
      setSpaceUploadFileName(String(parsed.spaceUploadFileName || ""))
      setAllowFractional(Boolean(parsed.allowFractional))
      setFractionalOverrides(
        parsed.fractionalOverrides && typeof parsed.fractionalOverrides === "object"
          ? parsed.fractionalOverrides
          : {}
      )
      setResults(null)
      setError(null)
      setSavedPortfolioStatus(t("manager.loadedPortfolio", "Saved portfolio loaded."))
    } catch {
      setSavedPortfolioStatus(
        t("manager.loadPortfolioError", "Saved portfolio could not be loaded.")
      )
    }
  }

  const handleSpaceFileUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return

    setSpaceUploadError(null)
    setSpaceUploadFileName(file.name)

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setSpaceUploadError('Only .csv files are accepted.')
      setCustomTickers([])
      setSpaceUploadFileName('')
      e.target.value = ''
      return
    }

    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target.result
      const tickers = text
        .split(/[\r\n,]+/)
        .map((t) => t.trim())
        .filter((t) => t && !t.startsWith('\\') && !t.startsWith('{') && !t.startsWith('}'))
        .filter(t => !/^(symbol|ticker|name|company)$/i.test(t))
        .map(t => t.replace(/\\$/, ''))
        .filter(t => /^[A-Z0-9.\-^]+$/i.test(t))

      if (tickers.length === 0) {
        setSpaceUploadError('No valid ticker symbols found in the file.')
        setCustomTickers([])
      } else {
        setCustomTickers(tickers)
        setShowSpaceUploadModal(false)
      }
    }
    reader.onerror = () => {
      setSpaceUploadError('Failed to read the file.')
      setCustomTickers([])
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const handleClearSpaceUpload = () => {
    setCustomTickers([])
    setSpaceUploadFileName('')
    setSpaceUploadError(null)
    if (spaceCsvFileInputRef.current) spaceCsvFileInputRef.current.value = ''
  }

  const handleCloseSpaceUploadModal = () => {
    setShowSpaceUploadModal(false)
    if (customTickers.length === 0) {
      setTickerGroup('CURRENT_HOLDINGS')
    }
  }

  // Determine per-ticker fractional eligibility
  const isTickerFractional = (ticker) => fractionalOverrides[ticker] ?? allowFractional

  const handleToggleFractional = (ticker) => {
    setFractionalOverrides(prev => ({ ...prev, [ticker]: !isTickerFractional(ticker) }))
  }

  const handleAllowFractionalChange = (checked) => {
    setAllowFractional(checked)
    setFractionalOverrides({})
  }

  const handleDownloadCsv = () => {
    const dataLines = holdings.filter(h => h.ticker.trim() && h.quantity !== "");
    if (dataLines.length === 0) return;
    
    const csvContent = "TICKER,QUANTITY\n" + dataLines.map(h => `${h.ticker.toUpperCase()},${h.quantity}`).join("\n");
    downloadBlob("portfolio_holdings.csv", csvContent, "text/csv;charset=utf-8;")
  }

  const buildManagerExportSettings = () => ({
    current_holdings: buildHoldingsDict(),
    cash_injection: Number.parseFloat(cashInjection) || 0,
    start_date: startDate,
    end_date: endDate,
    risk_free_rate: Number.parseFloat(riskFreeRate) / 100,
    forecast_method: forecastMethod,
    optimization_method: optimizationMethod,
    forecast_horizon: Number.parseInt(forecastHorizon),
    min_history: Number.parseInt(minHistory),
    bl_tau: Number.parseFloat(blTau),
    ticker_group: tickerGroup,
    custom_tickers: customTickers,
    allow_fractional: allowFractional,
    fractional_overrides: fractionalOverrides,
  })

  const handleSaveResultPdf = () => {
    if (!results) return

    const previousDisplayMode = orderDisplayMode
    const previousTitle = document.title
    const exportBaseName = buildExportBaseName(results.portfolio_id)

    setOrderDisplayMode("all")
    document.title = `${exportBaseName}.pdf`

    window.setTimeout(() => {
      resultsPrintRef.current?.scrollIntoView({ block: "start" })
      window.print()

      window.setTimeout(() => {
        document.title = previousTitle
        setOrderDisplayMode(previousDisplayMode)
      }, 500)
    }, 0)
  }

  const handleDownloadPortfolioJson = () => {
    if (!results) return

    const exportedAtDate = new Date()
    const exportedAt = exportedAtDate.toISOString()
    const exportBaseName = buildExportBaseName(results.portfolio_id, exportedAtDate)
    const payload = buildPortfolioExportPayload({
      results,
      managerSettings: buildManagerExportSettings(),
      portfolioId: results.portfolio_id || exportBaseName,
      exportedAt,
    })

    downloadBlob(
      `${exportBaseName}.json`,
      JSON.stringify(payload, null, 2),
      "application/json;charset=utf-8;"
    )
  }

  const handleDownloadTargetHoldingsCsv = () => {
    if (!results) return

    const exportBaseName = buildExportBaseName(results.portfolio_id)
    downloadBlob(
      `${exportBaseName}-target-holdings.csv`,
      buildTargetHoldingsCsv(results),
      "text/csv;charset=utf-8;"
    )
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
        forecast_horizon: Number.parseInt(forecastHorizon),
        min_history: Number.parseInt(minHistory),
        bl_tau: Number.parseFloat(blTau),
        allow_fractional: allowFractional,
        fractional_overrides: fractionalOverrides
      }
      
      if (tickerGroup === "CUSTOM") {
        if (customTickers.length > 0) {
          payload.tickers = customTickers
        }
      } else if (tickerGroup !== "CURRENT_HOLDINGS") {
        payload.ticker_group = tickerGroup
      }

      const response = await axios.post(
        apiUrl("/api/manage-portfolio"),
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

  const resultsDisplayData = useMemo(() => (
    results
      ? {
          ...results,
          asset_names: {
            ...(results.asset_names || {}),
            ...assetNameOverrides,
          },
        }
      : null
  ), [results, assetNameOverrides])

  const formatResultTicker = (ticker) => formatSecurityDisplay(ticker, resultsDisplayData, securityDisplayMode)

  useEffect(() => {
    if (securityDisplayMode !== "name" || !results) return

    const displayTickers = new Set([
      ...Object.keys(results.weights || {}),
      ...Object.keys(results.current_holdings || {}),
      ...Object.keys(results.buy_list || {}),
      ...Object.keys(results.sell_list || {}),
    ])
    const missingNameTickers = Array.from(displayTickers).filter(
      (ticker) =>
        getSecurityDisplayName(ticker, resultsDisplayData) === ticker &&
        assetNameOverrides[ticker] !== ticker
    )
    if (missingNameTickers.length === 0) return

    let cancelled = false
    fetchSecurityNames(missingNameTickers).then((names) => {
      if (!cancelled) {
        setAssetNameOverrides(prev => ({ ...prev, ...names }))
      }
    })

    return () => {
      cancelled = true
    }
  }, [securityDisplayMode, results, resultsDisplayData, assetNameOverrides])

  // --- Chart helpers ---
  const buildCurrentPieData = () => {
    if (!results || !results.prices) return null
    const holdingsDict = buildHoldingsDict()
    const labels = []
    const values = []
    for (const [ticker, qty] of Object.entries(holdingsDict)) {
      const price = results.prices[ticker] || 0
      labels.push(formatResultTicker(ticker))
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
        labels.push(formatResultTicker(ticker))
        values.push(weight * totalTarget)
      }
    }
    return { labels, values }
  }

  const chartLayout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#f4f1e8", family: "Outfit, Pretendard, sans-serif" },
    margin: { t: 40, b: 20, l: 20, r: 20 },
    showlegend: true,
    legend: { font: { size: 11 } },
    height: 350,
  }
  const chartPalette = [
    "#a8c77a", "#d6a85f", "#9ec979", "#e06d5f", "#aeb49f",
    "#c1a57b", "#87946f", "#b7cf8a", "#d0b17a", "#8fa66b",
  ]

  const currentPie = buildCurrentPieData()
  const targetPie = buildTargetPieData()
  const expectedReturn = results?.expected_return ?? results?.return
  const volatility = results?.volatility ?? results?.risk
  const sharpeRatio = results?.sharpe_ratio
  const formatPercentMetric = (value) => {
    const numericValue = Number(value)
    return Number.isFinite(numericValue) ? `${(numericValue * 100).toFixed(2)}%` : "N/A"
  }
  const formatRatioMetric = (value) => {
    const numericValue = Number(value)
    return Number.isFinite(numericValue) ? numericValue.toFixed(2) : "N/A"
  }

  return (
    <div className="manager-container">
      <h2 className="page-header">{t("manager.title", "Portfolio Manager")}</h2>

      <div className="optimizer-actions-row" style={{ marginBottom: "1rem" }}>
        <button
          className="optimizer-secondary-button"
          type="button"
          onClick={handleSavePortfolio}
        >
          {t("manager.saveInputsLocally", "Save Inputs Locally")}
        </button>
        <button
          className="optimizer-secondary-button"
          type="button"
          onClick={handleLoadPortfolio}
          disabled={!hasSavedPortfolio}
        >
          {t("manager.loadPortfolio", "Load Saved Portfolio")}
        </button>
        <button 
          className="optimizer-secondary-button" 
          type="button" 
          onClick={() => setShowAdvanced(true)}>
          {t("optimizer.advancedSettings", "Advanced Settings")}
        </button>
      </div>
      {savedPortfolioStatus && (
        <div className="manager-save-status" role="status">
          {savedPortfolioStatus}
        </div>
      )}

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
            <label>{t("optimizer.tickerGroup", "Target Asset Space")}</label>
            {tickerGroup === "CUSTOM" && customTickers.length > 0 ? (
              <button
                type="button"
                className="optimizer-select"
                onClick={() => setShowSpaceUploadModal(true)}
                style={{ cursor: 'pointer', textAlign: 'left' }}
              >
                {spaceUploadFileName} ({customTickers.length})
              </button>
            ) : (
              <select
                className="optimizer-select"
                value={tickerGroup}
                onChange={(e) => {
                  setTickerGroup(e.target.value)
                  if (e.target.value === 'CUSTOM') {
                    setShowSpaceUploadModal(true)
                  } else {
                    handleClearSpaceUpload()
                  }
                }}
                required
              >
                <option value="CURRENT_HOLDINGS">{t("manager.currentHoldingsOnly", "Current Holdings Only")}</option>
                <option value="SP500">S&P 500 (+ Holdings)</option>
                <option value="DOW">Dow Jones (+ Holdings)</option>
                <option value="CUSTOM">{t("optimizer.custom", "Custom CSV Upload")}</option>
              </select>
            )}
          </div>

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
              <option value="ARIMA_TRANSFORMER">
                {t("optimizer.ensemble", "ARIMA + Transformer")}
              </option>
              <option value="TRANSFORMER">
                {t("optimizer.transformer", "Transformer")}
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

      {showAdvanced && (
        <div className="optimizer-modal-overlay" onClick={() => setShowAdvanced(false)}>
          <div className="optimizer-modal-content optimizer-advanced-modal" onClick={e => e.stopPropagation()}>
            <div className="optimizer-modal-header">
              <h3 className="optimizer-modal-title">{t("optimizer.advancedSettings", "Advanced Settings")}</h3>
              <button type="button" className="optimizer-modal-close" onClick={() => setShowAdvanced(false)}>×</button>
            </div>
            <div className="optimizer-modal-body optimizer-advanced-modal-body">
              <div className="optimizer-advanced-section">
                <h4 className="optimizer-advanced-section-title">
                  {t("manager.csvTools", "CSV Tools")}
                </h4>
                <div className="manager-advanced-actions">
                  <button
                    className="optimizer-secondary-button"
                    type="button"
                    onClick={() => {
                      setShowAdvanced(false)
                      setShowUploadModal(true)
                    }}
                  >
                    {t("manager.uploadCsv", "Upload Holdings CSV")}
                  </button>
                  <button
                    className="optimizer-secondary-button"
                    type="button"
                    onClick={handleDownloadCsv}
                  >
                    {t("manager.downloadCsv", "Download Holdings CSV")}
                  </button>
                </div>
              </div>

              <div className="optimizer-advanced-section">
                <div className="optimizer-form-group">
                  <label htmlFor="forecastHorizon" title="Number of trading days to forecast into the future. Default is 63 (roughly one quarter).">{t("optimizer.forecastHorizon", "Forecast Horizon (Days)")}</label>
                  <input
                    id="forecastHorizon"
                    className="optimizer-input"
                    type="number"
                    value={forecastHorizon}
                    onChange={(e) => setForecastHorizon(e.target.value)}
                    placeholder="63"
                  />
                </div>

                <div className="optimizer-form-group">
                  <label htmlFor="minHistory" title="Minimum number of historical data points required for a ticker to be included.">{t("optimizer.minHistory", "Min. Data History (Days)")}</label>
                  <input
                    id="minHistory"
                    className="optimizer-input"
                    type="number"
                    value={minHistory}
                    onChange={(e) => setMinHistory(e.target.value)}
                    placeholder="504"
                  />
                </div>

                {optimizationMethod === "BL" && (
                  <div className="optimizer-form-group">
                    <label htmlFor="blTau" title="A scalar indicating the uncertainty of the CAPM prior (0 to 1). Lower values mean higher confidence in the market equilibrium. Standard default is 0.05.">{t("optimizer.blTau", "Black-Litterman Tau")}</label>
                    <input
                      id="blTau"
                      className="optimizer-input"
                      type="number"
                      step="0.01"
                      value={blTau}
                      onChange={(e) => setBlTau(e.target.value)}
                      placeholder="0.05"
                    />
                    <small style={{ display: 'block', marginTop: '4px', color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                      {t("optimizer.blTauHelp", "Confidence in market equilibrium: Lower = Higher Confidence")}
                    </small>
                  </div>
                )}
              </div>
            </div>
            <div className="optimizer-modal-footer">
              <button type="button" className="optimizer-secondary-button" onClick={() => setShowAdvanced(false)}>{t("common.done", "Done")}</button>
            </div>
          </div>
        </div>
      )}

      {showSpaceUploadModal && (
        <div className="optimizer-modal-overlay" onClick={handleCloseSpaceUploadModal}>
          <div className="optimizer-modal-content" onClick={e => e.stopPropagation()}>
            <div className="optimizer-modal-header">
              <h3 className="optimizer-modal-title">{t("optimizer.uploadCustomTickers", "Upload Custom Tickers")}</h3>
              <button type="button" className="optimizer-modal-close" onClick={handleCloseSpaceUploadModal}>×</button>
            </div>
            <div className="optimizer-modal-body">
              <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginBottom: 'var(--spacing-md)' }}>
                Upload a .csv file containing ticker symbols (one per line or comma-separated). Symbol or Ticker header rows are automatically ignored.
              </p>
              <button
                type="button"
                className="optimizer-secondary-button"
                onClick={() => spaceCsvFileInputRef.current?.click()}
                style={{ width: '100%', marginBottom: 'var(--spacing-md)' }}
              >
                {spaceUploadFileName ? t("optimizer.changeFile", "Change File") : t("optimizer.chooseCsvFile", "Choose CSV File")}
              </button>
              <input
                type="file"
                accept=".csv"
                ref={spaceCsvFileInputRef}
                style={{ display: 'none' }}
                onChange={handleSpaceFileUpload}
              />
              {spaceUploadError && (
                <div style={{ fontSize: '0.85rem', color: 'var(--color-danger)', marginBottom: 'var(--spacing-md)' }}>
                  {spaceUploadError}
                </div>
              )}
              {customTickers.length > 0 && (
                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                  <strong>{spaceUploadFileName}</strong> — {customTickers.length} ticker{customTickers.length !== 1 ? 's' : ''} loaded
                  <ul className="optimizer-weights-list" style={{ marginTop: 'var(--spacing-sm)', maxHeight: '150px' }}>
                    {customTickers.map(t => <li key={t}><span>{t}</span></li>)}
                  </ul>
                </div>
              )}
            </div>
            <div className="optimizer-modal-footer">
              {customTickers.length > 0 && (
                <button type="button" className="optimizer-secondary-button" onClick={handleClearSpaceUpload}>
                  {t("common.clear", "Clear")}
                </button>
              )}
              <button type="button" className="optimizer-secondary-button" onClick={handleCloseSpaceUploadModal}>
                {t("common.done", "Done")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="optimizer-error">
          <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
            {t("common.error", "Error")}
          </div>
          <div>{error}</div>
        </div>
      )}

      {loading && <ManagerSkeleton />}

      {/* Results */}
      {!loading && results && (
        <div className="manager-results" ref={resultsPrintRef}>
          <h3 className="manager-results-title">
            {t("manager.resultsTitle", "Rebalancing Results")}
          </h3>

          <div className="manager-results-actions no-print">
            <button
              className="optimizer-secondary-button"
              type="button"
              onClick={handleSaveResultPdf}
            >
              {t("manager.saveResultPdf", "Save Result as PDF")}
            </button>
            <button
              className="optimizer-secondary-button"
              type="button"
              onClick={handleDownloadPortfolioJson}
            >
              {t("manager.downloadPortfolioJson", "Download Portfolio JSON")}
            </button>
            <button
              className="optimizer-secondary-button"
              type="button"
              onClick={handleDownloadTargetHoldingsCsv}
            >
              {t("manager.downloadTargetHoldingsCsv", "Download New Holdings CSV")}
            </button>
          </div>

          <div className="manager-display-toggle no-print">
            <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginRight: '0.25rem' }}>
              {t("optimizer.securityDisplay", "Show:")}
            </span>
            {[
              { key: "ticker", label: t("optimizer.displayTicker", "Ticker") },
              { key: "name", label: t("optimizer.displayName", "Name") },
            ].map(mode => (
              <button
                key={mode.key}
                type="button"
                onClick={() => setSecurityDisplayMode(mode.key)}
                className={`manager-display-toggle-button ${securityDisplayMode === mode.key ? "optimizer-submit-button" : "optimizer-secondary-button"}`}
                style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem', minWidth: 'unset' }}
              >
                {mode.label}
              </button>
            ))}
          </div>

          <div className="optimizer-weights-card manager-fractional-card no-print">
            <div className="manager-fractional-header">
              <h4>{t("optimizer.fractionalSettings", "Fractional Settings")}</h4>
              <label className="manager-fractional-global-toggle">
                <input
                  type="checkbox"
                  checked={allowFractional}
                  onChange={(e) => handleAllowFractionalChange(e.target.checked)}
                />
                {t("optimizer.allowFractional", "Allow Fractional Shares (Global)")}
              </label>
            </div>
            
            <div className="manager-fractional-note">
              <p>Re-configure how non-fractional orders behave by overriding settings below, and resubmit.</p>
            </div>
            <ul className="optimizer-weights-list manager-fractional-list">
              {Array.from(new Set([...Object.keys(results.weights || {}), ...Object.keys(results.current_holdings || {})])).sort().map(ticker => {
                if (!ticker || (!results.weights?.[ticker] && !results.current_holdings?.[ticker])) return null;
                return (
                  <li key={ticker} className="manager-fractional-item">
                    <span className="manager-fractional-ticker">{formatResultTicker(ticker)}</span>
                    <label className="manager-fractional-toggle">
                      <input
                        type="checkbox"
                        checked={isTickerFractional(ticker)}
                        onChange={() => handleToggleFractional(ticker)}
                      />
                      {t("optimizer.fractionalAllowed", "Fractional Allowed")}
                    </label>
                  </li>
                )
              })}
            </ul>
            <button type="button" className="optimizer-submit-button manager-fractional-recalculate" onClick={handleSubmit} disabled={loading}>
              {loading ? t("common.processing", "Processing...") : t("manager.recalculate", "Recalculate Orders")}
            </button>
          </div>

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
                      textfont: { size: 11, color: "#f4f1e8" },
                      marker: {
                        colors: chartPalette,
                      },
                    },
                  ]}
                  layout={{
                    ...chartLayout,
                    title: { text: t("manager.currentAllocation", "Current Allocation"), font: { color: "#f4f1e8", size: 14 } },
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
                      textfont: { size: 11, color: "#f4f1e8" },
                      marker: {
                        colors: chartPalette,
                      },
                    },
                  ]}
                  layout={{
                    ...chartLayout,
                    title: { text: t("manager.targetAllocation", "Target Allocation"), font: { color: "#f4f1e8", size: 14 } },
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: "100%" }}
                />
              </div>
            )}
          </div>

          {/* Order Display Toggle */}
          {(results.buy_list && Object.keys(results.buy_list).length > 0) || (results.sell_list && Object.keys(results.sell_list).length > 0) ? (
            <div className="manager-display-toggle no-print">
              <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginRight: '0.25rem' }}>{t("manager.displayMode", "Display:")} </span>
              {[{key: 'all', label: t("manager.displayAll", "All")}, {key: 'shares', label: t("optimizer.shares", "Shares")}, {key: 'value', label: t("optimizer.investmentAmount", "Value")}].map(mode => (
                <button
                  key={mode.key}
                  type="button"
                  onClick={() => setOrderDisplayMode(mode.key)}
                  className={`manager-display-toggle-button ${orderDisplayMode === mode.key ? "optimizer-submit-button" : "optimizer-secondary-button"}`}
                  style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem', minWidth: 'unset' }}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          ) : null}

          {/* Buy List */}
          {results.buy_list && Object.keys(results.buy_list).length > 0 && (
            <div className="manager-order-section">
              <h4 className="manager-order-title manager-buy-title">
                {t("manager.buyList", "Buy List")}
              </h4>
              <table className="allocation-table">
                <thead>
                  <tr>
                    <th>
                      {securityDisplayMode === "name"
                        ? t("optimizer.securityName", "Name")
                        : t("optimizer.ticker", "Ticker")}
                    </th>
                    {(orderDisplayMode === 'all' || orderDisplayMode === 'shares') && <th>{t("optimizer.shares", "Shares")}</th>}
                    <th>{t("optimizer.price", "Price")}</th>
                    {(orderDisplayMode === 'all' || orderDisplayMode === 'value') && <th>{t("optimizer.investmentAmount", "Value")}</th>}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(results.buy_list).map(([ticker, data]) => (
                    <tr key={ticker}>
                      <td className="ticker-cell">{formatResultTicker(ticker)}</td>
                      {(orderDisplayMode === 'all' || orderDisplayMode === 'shares') && (
                        <td className="number-cell">
                          {data.quantity?.toFixed(4)}
                        </td>
                      )}
                      <td className="number-cell">
                        ${data.price?.toFixed(2)}
                      </td>
                      {(orderDisplayMode === 'all' || orderDisplayMode === 'value') && (
                        <td className="number-cell positive">
                          +${data.value?.toFixed(2)}
                        </td>
                      )}
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
                    <th>
                      {securityDisplayMode === "name"
                        ? t("optimizer.securityName", "Name")
                        : t("optimizer.ticker", "Ticker")}
                    </th>
                    {(orderDisplayMode === 'all' || orderDisplayMode === 'shares') && <th>{t("optimizer.shares", "Shares")}</th>}
                    <th>{t("optimizer.price", "Price")}</th>
                    {(orderDisplayMode === 'all' || orderDisplayMode === 'value') && <th>{t("optimizer.investmentAmount", "Value")}</th>}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(results.sell_list).map(([ticker, data]) => (
                    <tr key={ticker}>
                      <td className="ticker-cell">{formatResultTicker(ticker)}</td>
                      {(orderDisplayMode === 'all' || orderDisplayMode === 'shares') && (
                        <td className="number-cell">
                          {data.quantity?.toFixed(4)}
                        </td>
                      )}
                      <td className="number-cell">
                        ${data.price?.toFixed(2)}
                      </td>
                      {(orderDisplayMode === 'all' || orderDisplayMode === 'value') && (
                        <td className="number-cell negative">
                          -${data.value?.toFixed(2)}
                        </td>
                      )}
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
                      <span>{formatResultTicker(ticker)}</span>
                      <strong>{(weight * 100).toFixed(2)}%</strong>
                    </li>
                  ))}
              </ul>
            </div>
          )}

          {/* Total Target Value */}
          {results.total_target_value !== undefined && (
            <div className="manager-summary-grid">
              <div className="manager-summary-card manager-summary-card-wide">
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
              <div className="manager-summary-card manager-summary-metric-card">
                <span className="manager-summary-label">
                  {t("optimizer.return", "Expected Return")}
                </span>
                <span className="manager-summary-metric-value">
                  {formatPercentMetric(expectedReturn)}
                </span>
              </div>
              <div className="manager-summary-card manager-summary-metric-card">
                <span className="manager-summary-label">
                  {t("optimizer.risk", "Volatility")}
                </span>
                <span className="manager-summary-metric-value">
                  {formatPercentMetric(volatility)}
                </span>
              </div>
              <div className="manager-summary-card manager-summary-metric-card">
                <span className="manager-summary-label">
                  {t("optimizer.sharpeRatio", "Sharpe Ratio")}
                </span>
                <span className="manager-summary-metric-value">
                  {formatRatioMetric(sharpeRatio)}
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default PortfolioManager
