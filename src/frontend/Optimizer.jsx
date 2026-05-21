"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"
import { fetchSecurityNames, formatSecurityDisplay, getSecurityDisplayName } from "./securityDisplay"
import { apiUrl } from "./apiClient.js"

const Optimizer = () => {
  const { t } = useTranslation()
  const [tickerGroup, setTickerGroup] = useState("SP500")
  const [forecastMethod, setForecastMethod] = useState("LIGHTWEIGHT")
  const [optimizationMethod, setOptimizationMethod] = useState("BL")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [riskFreeRate, setRiskFreeRate] = useState("2")
  const [targetReturn, setTargetReturn] = useState("")
  const [riskTolerance, setRiskTolerance] = useState("")
  const [optimizedPortfolio, setOptimizedPortfolio] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [errorDetails, setErrorDetails] = useState(null)
  const [investmentAmount, setInvestmentAmount] = useState("")
  const [allocation, setAllocation] = useState(null)
  const [customTickers, setCustomTickers] = useState([])
  const [forecastHorizon, setForecastHorizon] = useState("63")
  const [minHistory, setMinHistory] = useState("504")
  const [blTau, setBlTau] = useState("0.05")
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [allowFractional, setAllowFractional] = useState(false)
  const [fractionalOverrides, setFractionalOverrides] = useState({})
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadFileName, setUploadFileName] = useState('')
  const [uploadError, setUploadError] = useState(null)
  const [securityDisplayMode, setSecurityDisplayMode] = useState("ticker")
  const [assetNameOverrides, setAssetNameOverrides] = useState({})
  const portfolioFileInputRef = useRef(null)
  const csvFileInputRef = useRef(null)

  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return

    setUploadError(null)
    setUploadFileName(file.name)

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setUploadError('Only .csv files are accepted.')
      setCustomTickers([])
      setUploadFileName('')
      e.target.value = ''
      return
    }

    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target.result
      const tickers = text
        .split(/[\r\n,]+/)
        .map((t) => t.trim())
        // Remove header rows, RTF artifacts, and empty lines
        .filter((t) => t && !t.startsWith('\\') && !t.startsWith('{') && !t.startsWith('}'))
        .filter(t => !/^(symbol|ticker|name|company)$/i.test(t))
        .map(t => t.replace(/\\$/, ''))
        // Allow only valid ticker characters
        .filter(t => /^[A-Z0-9.\-^]+$/i.test(t))

      if (tickers.length === 0) {
        setUploadError('No valid ticker symbols found in the file.')
        setCustomTickers([])
      } else {
        setCustomTickers(tickers)
      }
    }
    reader.onerror = () => {
      setUploadError('Failed to read the file.')
      setCustomTickers([])
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const handleClearUpload = () => {
    setCustomTickers([])
    setUploadFileName('')
    setUploadError(null)
    if (csvFileInputRef.current) csvFileInputRef.current.value = ''
  }

  const handleCloseUploadModal = () => {
    setShowUploadModal(false)
    if (customTickers.length === 0) {
      setTickerGroup('SP500')
    }
  }

  // Determine per-ticker fractional eligibility
  const isTickerFractional = useCallback(
    (ticker) => fractionalOverrides[ticker] ?? allowFractional,
    [allowFractional, fractionalOverrides],
  )

  const handleToggleFractional = (ticker) => {
    setFractionalOverrides(prev => ({ ...prev, [ticker]: !isTickerFractional(ticker) }))
  }

  const handleAllowFractionalChange = (checked) => {
    setAllowFractional(checked)
    // Reset per-ticker overrides so they all follow the global toggle
    setFractionalOverrides({})
  }

  const handleAllocation = useCallback(() => {
    if (!investmentAmount || !optimizedPortfolio || !optimizedPortfolio.weights) return

    const totalInvestment = Number.parseFloat(investmentAmount)
    const weights = optimizedPortfolio.weights
    const prices = optimizedPortfolio.prices || {}

    // Step 1: Allocate per-ticker based on fractional eligibility
    const entries = Object.entries(weights).map(([ticker, weight]) => {
      const price = prices[ticker] ?? 1
      const idealAmount = totalInvestment * weight
      const idealShares = idealAmount / price
      const fractional = isTickerFractional(ticker)

      if (fractional) {
        return { ticker, weight, price, shares: idealShares, amount: idealAmount, fractional: true }
      }
      const floorShares = Math.floor(idealShares)
      return { ticker, weight, price, shares: floorShares, amount: floorShares * price, fractional: false }
    })

    // Step 2: Calculate freed capital from integer rounding
    let spent = entries.reduce((sum, e) => sum + e.amount, 0)
    let remaining = totalInvestment - spent

    if (remaining > 0.01) {
      // Step 3: Redistribute remaining to fractional-eligible tickers proportionally
      const fractionalEntries = entries.filter(e => e.fractional)
      const fractionalWeight = fractionalEntries.reduce((sum, e) => sum + e.weight, 0)

      if (fractionalWeight > 0 && remaining > 0.01) {
        for (const entry of fractionalEntries) {
          const extra = (entry.weight / fractionalWeight) * remaining
          entry.shares += extra / entry.price
          entry.amount += extra
        }
        remaining = 0
      }

      // Step 4: If no fractional tickers absorbed it, try whole shares (greedy by weight)
      if (remaining > 0.01) {
        let changed = true
        while (changed && remaining > 0.01) {
          changed = false
          const sorted = [...entries].filter(e => !e.fractional).sort((a, b) => b.weight - a.weight)
          for (const entry of sorted) {
            if (entry.price <= remaining) {
              entry.shares += 1
              entry.amount = entry.shares * entry.price
              remaining -= entry.price
              changed = true
              break
            }
          }
        }
      }
    }

    setAllocation({ items: entries, remainingCash: Math.max(0, remaining) })
  }, [investmentAmount, isTickerFractional, optimizedPortfolio])

  // Auto-calculate allocation when fractional settings change
  const hasAllocation = allocation !== null
  useEffect(() => {
    if (hasAllocation) {
      handleAllocation()
    }
  }, [handleAllocation, hasAllocation])

  const handleDownloadPortfolio = () => {
    if (!optimizedPortfolio) return
    const payload = {
      ...optimizedPortfolio,
      portfolio_id: optimizedPortfolio.portfolio_id || `portfolio_${Date.now()}`,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${payload.portfolio_id}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const triggerPortfolioUpload = () => {
    portfolioFileInputRef.current?.click()
  }

  const handlePortfolioUpload = (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result)
        if (!parsed || typeof parsed !== "object" || !parsed.weights) {
          throw new Error("Invalid portfolio file: missing weights")
        }
        setOptimizedPortfolio(parsed)
        setAllocation(null)
        setError(null)
      } catch (uploadError) {
        setError(uploadError.message || "Failed to load portfolio file")
      }
    }
    reader.onerror = () => setError("Failed to read portfolio file")
    reader.readAsText(file)

    // Reset input value to allow uploading the same file again if needed
    event.target.value = ""
  }

  const [progress, setProgress] = useState(null)

  const generateRequestId = () => `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

  const portfolioDisplayData = useMemo(() => (
    optimizedPortfolio
      ? {
          ...optimizedPortfolio,
          asset_names: {
            ...(optimizedPortfolio.asset_names || {}),
            ...assetNameOverrides,
          },
        }
      : null
  ), [optimizedPortfolio, assetNameOverrides])

  const formatPortfolioTicker = (ticker) =>
    formatSecurityDisplay(ticker, portfolioDisplayData, securityDisplayMode)

  useEffect(() => {
    if (securityDisplayMode !== "name" || !optimizedPortfolio?.weights) return

    const missingNameTickers = Object.keys(optimizedPortfolio.weights).filter(
      (ticker) =>
        getSecurityDisplayName(ticker, portfolioDisplayData) === ticker &&
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
  }, [securityDisplayMode, optimizedPortfolio, portfolioDisplayData, assetNameOverrides])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setErrorDetails(null)
    setOptimizedPortfolio(null)
    setAllocation(null)
    setProgress({ percentage: 0, message: t("common.starting", "Starting...") })

    const requestId = generateRequestId()

    try {
      const payload = {
        start_date: startDate,
        end_date: endDate,
        risk_free_rate: Number.parseFloat(riskFreeRate) / 100,
        target_return: targetReturn ? Number.parseFloat(targetReturn) / 100 : null,
        risk_tolerance: riskTolerance ? Number.parseFloat(riskTolerance) / 100 : null,
        request_id: requestId,
        forecast_method: forecastMethod,
        optimization_method: optimizationMethod,
        forecast_horizon: Number.parseInt(forecastHorizon),
        min_history: Number.parseInt(minHistory),
        bl_tau: Number.parseFloat(blTau)
      }

      if (tickerGroup === "CUSTOM") {
        payload.tickers = customTickers
      } else {
        payload.ticker_group = tickerGroup
      }

      // Start SSE connection
      const eventSource = new EventSource(apiUrl(`/api/progress-stream/${encodeURIComponent(requestId)}`))

      eventSource.onmessage = () => {
        // Ping/Keep-alive, ignore
      }

      eventSource.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data)
        setProgress({ percentage: data.progress, message: data.message })
      })

      eventSource.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data)
        setProgress({ percentage: 100, message: 'Optimization complete!' })
        eventSource.close()

        // The result is passed in the complete event for simplicity in this refactor
        if (data.result) {
          setOptimizedPortfolio(data.result)
        }
        setLoading(false)
      })

      eventSource.addEventListener('error', (e) => {
        if (e.data) {
          const data = JSON.parse(e.data)
          setError(data.message)
        } else {
          // Connection error or stream closed unexpectedly
          // setError("Stream connection lost") 
        }
        eventSource.close()
        setLoading(false)
      })

      // Initiate optimization
      await axios.post(apiUrl("/api/optimize-portfolio"), payload)

    } catch (err) {
      if (import.meta.env.DEV) {
        console.error(err)
      }
      if (err.response && err.response.data) {
        setError(err.response.data.error || "An error occurred starting optimization")
        setErrorDetails(err.response.data.details || null)
      } else {
        setError("An error occurred starting optimization")
        setErrorDetails(err.message)
      }
      setOptimizedPortfolio(null)
      setLoading(false)
    }
  }

  return (
    <div className="optimizer-container">
      <h2 className="page-header">{t("optimizer.title")}</h2>
      <div className="optimizer-actions-row" style={{ marginBottom: "1rem" }}>
        <button className="optimizer-secondary-button" type="button" onClick={triggerPortfolioUpload}>
          {t("optimizer.loadPortfolio", "Load JSON")}
        </button>
        <button className="optimizer-secondary-button" type="button" onClick={() => setShowAdvanced(true)}>
          {t("optimizer.advancedSettings", "Advanced Settings")}
        </button>
        <input
          type="file"
          accept="application/json"
          ref={portfolioFileInputRef}
          style={{ display: "none" }}
          onChange={handlePortfolioUpload}
        />
      </div>
      <form onSubmit={handleSubmit} className="optimizer-form">
        <div className="optimizer-form-grid">
          <div className="optimizer-form-group">
            <label>{t("optimizer.tickerGroup")}</label>
            {tickerGroup === "CUSTOM" && customTickers.length > 0 ? (
              <button
                type="button"
                className="optimizer-select"
                onClick={() => setShowUploadModal(true)}
                style={{ cursor: 'pointer', textAlign: 'left' }}
              >
                {uploadFileName} ({customTickers.length})
              </button>
            ) : (
              <select
                className="optimizer-select"
                value={tickerGroup}
                onChange={(e) => {
                  setTickerGroup(e.target.value)
                  if (e.target.value === 'CUSTOM') {
                    setShowUploadModal(true)
                  } else {
                    handleClearUpload()
                  }
                }}
                required
              >
                <option value="SP500">S&P 500</option>
                <option value="DOW">Dow Jones</option>
                <option value="CUSTOM">{t("optimizer.custom")}</option>
              </select>
            )}
          </div>

          <div className="optimizer-form-group">
            <label htmlFor="forecastMethod">{t("optimizer.forecastMethod", "Forecast Method")}</label>
            <select
              id="forecastMethod"
              className="optimizer-select"
              value={forecastMethod}
              onChange={(e) => setForecastMethod(e.target.value)}
            >
              <option value="LIGHTWEIGHT">{t("optimizer.lightweight", "Lightweight Prediction")}</option>
              <option value="ARIMA_TRANSFORMER">{t("optimizer.ensemble", "ARIMA + Transformer")}</option>
              <option value="TRANSFORMER">{t("optimizer.transformer", "Transformer")}</option>
            </select>
          </div>

          <div className="optimizer-form-group">
            <label htmlFor="optimizationMethod">{t("optimizer.optimizationMethod", "Optimization Method")}</label>
            <select
              id="optimizationMethod"
              className="optimizer-select"
              value={optimizationMethod}
              onChange={(e) => setOptimizationMethod(e.target.value)}
            >
              <option value="BL">{t("optimizer.bl", "Black-Litterman")}</option>
              <option value="MPT">{t("optimizer.mpt", "Mean-Variance (MPT)")}</option>
            </select>
          </div>

          <div className="optimizer-form-group">
            <label htmlFor="startDate">{t("optimizer.startDate")}</label>
            <input
              id="startDate"
              className="optimizer-input"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
          </div>
          <div className="optimizer-form-group">
            <label htmlFor="endDate">{t("optimizer.endDate")}</label>
            <input
              id="endDate"
              className="optimizer-input"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              required
            />
          </div>
          <div className="optimizer-form-group">
            <label htmlFor="riskFreeRate">{t("optimizer.riskFreeRate")}</label>
            <div className="input-with-symbol">
              <input
                id="riskFreeRate"
                className="optimizer-input"
                type="number"
                value={riskFreeRate}
                onChange={(e) => setRiskFreeRate(e.target.value)}
                placeholder="e.g., 2"
                required
              />
            </div>
          </div>
          <button type="submit" className="optimizer-submit-button" disabled={loading}>
            {loading ? t("common.processing", "Processing...") : t("optimizer.submit")}
          </button>

          {showAdvanced && (
            <div className="optimizer-modal-overlay" onClick={() => setShowAdvanced(false)}>
              <div className="optimizer-modal-content optimizer-advanced-modal" onClick={e => e.stopPropagation()}>
                <div className="optimizer-modal-header">
                  <h3 className="optimizer-modal-title">{t("optimizer.advancedSettings", "Advanced Settings")}</h3>
                  <button type="button" className="optimizer-modal-close" onClick={() => setShowAdvanced(false)}>×</button>
                </div>
                <div className="optimizer-modal-body optimizer-advanced-modal-body">
                  <div className="optimizer-advanced-section">
                    <div className="optimizer-advanced-section-title">{t("optimizer.constraints", "Constraints")}</div>
                    <div className="optimizer-advanced-grid">
                      <div className="optimizer-form-group">
                        <label htmlFor="targetReturn">{t("optimizer.targetReturn")}</label>
                        <div className="input-with-symbol">
                          <input
                            id="targetReturn"
                            className="optimizer-input"
                            type="number"
                            value={targetReturn}
                            onChange={(e) => {
                              setTargetReturn(e.target.value)
                              if (e.target.value) setRiskTolerance("")
                            }}
                            placeholder="e.g., 20"
                          />
                        </div>
                      </div>

                      <div className="optimizer-form-group">
                        <label htmlFor="riskTolerance">{t("optimizer.riskTolerance")}</label>
                        <div className="input-with-symbol">
                          <input
                            id="riskTolerance"
                            className="optimizer-input"
                            type="number"
                            value={riskTolerance}
                            onChange={(e) => {
                              setRiskTolerance(e.target.value)
                              if (e.target.value) setTargetReturn("")
                            }}
                            placeholder="e.g., 15"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="optimizer-advanced-section">
                    <div className="optimizer-advanced-section-title">{t("optimizer.forecastControls", "Forecast Controls")}</div>
                    <div className="optimizer-advanced-grid">
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
                        <div className="optimizer-form-group optimizer-advanced-field-wide">
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
                          <small className="optimizer-field-help">
                            {t("optimizer.blTauHelp", "Confidence in market equilibrium: Lower = Higher Confidence")}
                          </small>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <div className="optimizer-modal-footer">
                  <button type="button" className="optimizer-secondary-button" onClick={() => setShowAdvanced(false)}>{t("common.done", "Done")}</button>
                </div>
              </div>
            </div>
          )}

          {showUploadModal && (
            <div className="optimizer-modal-overlay" onClick={handleCloseUploadModal}>
              <div className="optimizer-modal-content" onClick={e => e.stopPropagation()}>
                <div className="optimizer-modal-header">
                  <h3 className="optimizer-modal-title">{t("optimizer.uploadCustomTickers", "Upload Custom Tickers")}</h3>
                  <button type="button" className="optimizer-modal-close" onClick={handleCloseUploadModal}>×</button>
                </div>
                <div className="optimizer-modal-body">
                  <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginBottom: 'var(--spacing-md)' }}>
                    Upload a .csv file containing ticker symbols (one per line or comma-separated). Header rows like &quot;Symbol&quot; or &quot;Ticker&quot; are automatically ignored.
                  </p>
                  <button
                    type="button"
                    className="optimizer-secondary-button"
                    onClick={() => csvFileInputRef.current?.click()}
                    style={{ width: '100%', marginBottom: 'var(--spacing-md)' }}
                  >
                    {uploadFileName ? t("optimizer.changeFile", "Change File") : t("optimizer.chooseCsvFile", "Choose CSV File")}
                  </button>
                  <input
                    type="file"
                    accept=".csv"
                    ref={csvFileInputRef}
                    style={{ display: 'none' }}
                    onChange={handleFileUpload}
                  />
                  {uploadError && (
                    <div style={{ fontSize: '0.85rem', color: 'var(--color-danger)', marginBottom: 'var(--spacing-md)' }}>
                      {uploadError}
                    </div>
                  )}
                  {customTickers.length > 0 && (
                    <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                      <strong>{uploadFileName}</strong> — {customTickers.length} ticker{customTickers.length !== 1 ? 's' : ''} loaded
                      <ul className="optimizer-weights-list" style={{ marginTop: 'var(--spacing-sm)', maxHeight: '150px' }}>
                        {customTickers.map(t => <li key={t}><span>{t}</span></li>)}
                      </ul>
                    </div>
                  )}
                </div>
                <div className="optimizer-modal-footer">
                  {customTickers.length > 0 && (
                    <button type="button" className="optimizer-secondary-button" onClick={handleClearUpload}>
                      {t("common.clear", "Clear")}
                    </button>
                  )}
                  <button type="button" className="optimizer-secondary-button" onClick={handleCloseUploadModal}>
                    {t("common.done", "Done")}
                  </button>
                </div>
              </div>
            </div>
          )}

          {loading && progress && (
            <div className="optimizer-progress-container" style={{
              marginTop: '1rem',
              width: '100%',
              gridColumn: '1 / -1',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <div className="optimizer-progress-bar-bg" style={{
                background: '#e0e0e0',
                borderRadius: '8px',
                height: '10px',
                overflow: 'hidden',
                width: '100%',
                maxWidth: '600px' // Optional: limit width for better aesthetics on wide screens
              }}>
                <div className="optimizer-progress-bar-fill" style={{
                  width: `${progress.percentage}%`,
                  background: '#4CAF50',
                  height: '100%',
                  transition: 'width 0.5s ease-in-out'
                }}></div>
              </div>
              <p style={{ textAlign: 'center', marginTop: '0.5rem', fontSize: '0.9rem', color: '#666' }}>
                {progress.percentage}% - {progress.message}
              </p>
            </div>
          )}
        </div>
      </form>

      {error && (
        <div className="optimizer-error" style={{ padding: '1rem', backgroundColor: '#fee2e2', border: '1px solid #ef4444', borderRadius: '6px', color: '#991b1b', marginBottom: '1rem' }}>
          <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{t("common.error", "Error")}</div>
          <div>{error}</div>
          {errorDetails && (
            <div style={{ marginTop: '0.5rem', fontSize: '0.875rem', opacity: 0.9, whiteSpace: 'pre-wrap' }}>
              {errorDetails}
            </div>
          )}
        </div>
      )}

      {optimizedPortfolio && (
        <>
          <div className="optimizer-results-container">
            <h3>{t("optimizer.results")}</h3>
            <div className="optimizer-actions-row">
              <button
                className="optimizer-secondary-button"
                onClick={handleDownloadPortfolio}
                disabled={!optimizedPortfolio}
                type="button"
              >
                {t("optimizer.downloadPortfolio", "Download JSON")}
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
            <div className="optimizer-results-grid">
              <div className="optimizer-result-card">
                <h4>{t("optimizer.return")}</h4>
                <p>{(optimizedPortfolio.return * 100).toFixed(2)}%</p>
              </div>
              <div className="optimizer-result-card">
                <h4>{t("optimizer.risk")}</h4>
                <p>{(optimizedPortfolio.risk * 100).toFixed(2)}%</p>
              </div>
              <div className="optimizer-result-card">
                <h4>{t("optimizer.sharpeRatio")}</h4>
                <p>{optimizedPortfolio.sharpe_ratio.toFixed(2)}</p>
              </div>
            </div>
            <div className="optimizer-weights-card">
              <h4>{t("optimizer.weights")}</h4>
              <ul className="optimizer-weights-list">
                {Object.entries(optimizedPortfolio.weights).map(([ticker, weight]) => (
                  <li key={ticker}>
                    <span>{formatPortfolioTicker(ticker)}</span>
                    <strong>{(weight * 100).toFixed(2)}%</strong>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="investment-allocation-container">
            <h3>{t("optimizer.investmentAllocation")}</h3>
            <div className="investment-allocation-form">
              <div className="optimizer-form-group">
                <label style={{ textAlign: 'center' }}>{t("optimizer.investmentBudget")}</label>
                <input
                  className="optimizer-input"
                  type="number"
                  value={investmentAmount}
                  onChange={(e) => setInvestmentAmount(e.target.value)}
                  placeholder={t("optimizer.enterBudget")}
                />
              </div>
              <div className="allocation-toggle-row">
                <label className="toggle-switch" htmlFor="allowFractional">
                  <input
                    id="allowFractional"
                    type="checkbox"
                    checked={allowFractional}
                    onChange={(e) => handleAllowFractionalChange(e.target.checked)}
                  />
                  <span className="toggle-slider" />
                  <span className="toggle-label">{t("optimizer.allowFractionalAll", "All Fractional Shares")}</span>
                </label>
              </div>
              <button onClick={handleAllocation} className="optimizer-submit-button">
                {t("optimizer.calculate")}
            </button>
            </div>
            
            {allocation && (
              <div className="allocation-results-container">
                <h4>{t("optimizer.allocationResults")}</h4>
                <table className="allocation-table">
                  <thead>
                    <tr>
                      <th>
                        {securityDisplayMode === "name"
                          ? t("optimizer.securityName", "Name")
                          : t("optimizer.ticker")}
                      </th>
                      <th>{t("optimizer.price", "Price")}</th>
                      <th>{t("optimizer.shares")}</th>
                      <th>{t("optimizer.investmentAmount")}</th>
                      <th>{t("optimizer.fractional", "Fractional")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allocation.items
                      .filter(({ ticker }) => optimizedPortfolio.weights[ticker] > 0.0001)
                      .map(({ ticker, price, amount, shares, fractional }) => (
                        <tr key={ticker}>
                          <td>{formatPortfolioTicker(ticker)}</td>
                          <td>${price.toFixed(2)}</td>
                          <td>{fractional ? shares.toFixed(4) : shares}</td>
                          <td>${amount.toFixed(2)}</td>
                          <td>
                            <label className="toggle-switch toggle-switch-sm">
                              <input
                                type="checkbox"
                                checked={isTickerFractional(ticker)}
                                onChange={() => handleToggleFractional(ticker)}
                              />
                              <span className="toggle-slider" />
                            </label>
                          </td>
                        </tr>
                      ))}
                    {allocation.remainingCash > 0.01 && (
                      <tr style={{ fontStyle: 'italic', opacity: 0.8 }}>
                        <td>{t("optimizer.remainingCash", "Remaining Cash")}</td>
                        <td>—</td>
                        <td>—</td>
                        <td>${allocation.remainingCash.toFixed(2)}</td>
                        <td />
                      </tr>
                    )}
                  </tbody>
                </table>
                <small style={{ display: 'block', marginTop: '0.5rem', color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                  {t("optimizer.hybridNote", "Toggle fractional per ticker. Integer-only tickers are floored; freed capital is redistributed to fractional-eligible tickers.")}
                </small>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default Optimizer
