"use client"

import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"

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
  const [investmentAmount, setInvestmentAmount] = useState("")
  const [allocation, setAllocation] = useState(null)
  const [customTickers, setCustomTickers] = useState([])
  const portfolioFileInputRef = useRef(null)

  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (file) {
      const reader = new FileReader()
      reader.onload = (event) => {
        const text = event.target.result
        const tickers = text
          .split("\n")
          .map((t) => t.trim())
          .filter((t) => t)
        setCustomTickers(tickers)
      }
      reader.readAsText(file)
    }
  }

  const handleAllocation = () => {
    if (!investmentAmount || !optimizedPortfolio || !optimizedPortfolio.weights) return

    const totalInvestment = Number.parseFloat(investmentAmount)
    const allocated = Object.entries(optimizedPortfolio.weights).map(([ticker, weight]) => {
      const amount = totalInvestment * weight
      // Assuming we can get price data, for now we'll use a placeholder
      // In a real scenario, you'd fetch current prices for each ticker
      const price = optimizedPortfolio.prices?.[ticker] ?? 1 // Placeholder price
      const shares = amount / price
      return { ticker, amount, shares }
    })
    setAllocation(allocated)
  }

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

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setOptimizedPortfolio(null)
    setAllocation(null)
    setProgress({ percentage: 0, message: t("common.starting", "Starting...") })

    const requestId = generateRequestId()
    let pollInterval

    try {
      const payload = {
        start_date: startDate,
        end_date: endDate,
        risk_free_rate: Number.parseFloat(riskFreeRate) / 100,
        target_return: targetReturn ? Number.parseFloat(targetReturn) / 100 : null,
        risk_tolerance: riskTolerance ? Number.parseFloat(riskTolerance) / 100 : null,
        request_id: requestId,
        forecast_method: forecastMethod,
        optimization_method: optimizationMethod
      }

      if (tickerGroup === "CUSTOM") {
        payload.tickers = customTickers
      } else {
        payload.ticker_group = tickerGroup
      }

      // Start SSE connection
      const eventSource = new EventSource(`http://127.0.0.1:5000/api/progress-stream/${requestId}`)

      eventSource.onmessage = (event) => {
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
      await axios.post("http://127.0.0.1:5000/api/optimize-portfolio", payload)

    } catch (err) {
      console.error(err)
      setError(err.response ? err.response.data.error : "An error occurred starting optimization")
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
            <select
              className="optimizer-select"
              value={tickerGroup}
              onChange={(e) => setTickerGroup(e.target.value)}
              required
            >
              <option value="SP500">S&P 500</option>
              <option value="DOW">Dow Jones</option>
              <option value="CUSTOM">{t("optimizer.custom")}</option>
            </select>
            {tickerGroup === "CUSTOM" && <input type="file" accept=".csv" onChange={handleFileUpload} />}
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
              <option value="DEEP_LEARNING">{t("optimizer.ensemble", "Deep Learning Ensemble")}</option>
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
            <label>{t("optimizer.startDate")}</label>
            <input
              className="optimizer-input"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />
          </div>
          <div className="optimizer-form-group">
            <label>{t("optimizer.endDate")}</label>
            <input
              className="optimizer-input"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              required
            />
          </div>
          <div className="optimizer-form-group">
            <label>{t("optimizer.riskFreeRate")}</label>
            <div className="input-with-symbol">
              <input
                className="optimizer-input"
                type="number"
                value={riskFreeRate}
                onChange={(e) => setRiskFreeRate(e.target.value)}
                placeholder="e.g., 2"
                required
              />
            </div>
          </div>
          <div className="optimizer-form-group">
            <label>{t("optimizer.targetReturn")}</label>
            <div className="input-with-symbol">
              <input
                className="optimizer-input"
                type="number"
                value={targetReturn}
                onChange={(e) => setTargetReturn(e.target.value)}
                placeholder="e.g., 20"
              />
            </div>
          </div>
          <div className="optimizer-form-group">
            <label>{t("optimizer.riskTolerance")}</label>
            <div className="input-with-symbol">
              <input
                className="optimizer-input"
                type="number"
                value={riskTolerance}
                onChange={(e) => setRiskTolerance(e.target.value)}
                placeholder="e.g., 15"
              />
            </div>
          </div>
          <button type="submit" className="optimizer-submit-button" disabled={loading}>
            {loading ? t("common.processing", "Processing...") : t("optimizer.submit")}
          </button>

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

      {error && <div className="optimizer-error">{error}</div>}

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
                    <span>{ticker}</span>
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
                <label>{t("optimizer.investmentBudget")}</label>
                <input
                  className="optimizer-input"
                  type="number"
                  value={investmentAmount}
                  onChange={(e) => setInvestmentAmount(e.target.value)}
                  placeholder={t("optimizer.enterBudget")}
                />
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
                      <th>{t("optimizer.ticker")}</th>
                      <th>{t("optimizer.investmentAmount")}</th>
                      <th>{t("optimizer.shares")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allocation
                      .filter(({ ticker }) => optimizedPortfolio.weights[ticker] > 0.0001)
                      .map(({ ticker, amount, shares }) => (
                        <tr key={ticker}>
                          <td>{ticker}</td>
                          <td>${amount.toFixed(2)}</td>
                          <td>{shares.toFixed(4)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default Optimizer
