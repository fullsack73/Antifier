"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { I18nextProvider, useTranslation } from "react-i18next"
import i18n from "./config/i18n"
import StockChart from "./StockChart.jsx"
import DateInput from "./DateInput.jsx"
import TickerInput from "./TickerInput.jsx"
import ModelSelector from "./ModelSelector.jsx"
import RegressionChart from "./RegressionChart.jsx"
import Selector from "./Selector.jsx"
import HedgeAnalysis from "./Hedge.jsx"
import LanguageSelector from "./LanguageSelector.jsx"
import FutureDateInput from "./FutureDateInput.jsx"
import FutureChart from "./FutureChart.jsx"
import FinancialStatement from "./FinancialStatement.jsx"
import Optimizer from "./Optimizer.jsx"
import PortfolioBenchmark from "./PortfolioBenchmark.jsx"
import PortfolioManager from "./PortfolioManager.jsx"
import { apiUrl } from "./apiClient.js"
import { clearOptimizerJob, isRunningOptimizerJob, readOptimizerJob, writeOptimizerJob } from "./optimizerJobStorage.js"
import { StockChartsSkeleton } from "./SkeletonScreens.jsx"
import { getCurrencyPair, invertCurrencySeries } from "./priceChartAxis.js"
import "./App.css"

const STOCK_FETCH_DEBOUNCE_MS = 1800
const OPTIMIZER_JOB_HEARTBEAT_MS = 30000

function AppContent() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [ticker, setTicker] = useState("AAPL")
  const [modelType, setModelType] = useState("LSTM")
  const [companyName, setCompanyName] = useState("Apple Inc.")
  const [showChart, setShowChart] = useState(false)
  const [regressionData, setRegressionData] = useState(null)
  const [formula, setFormula] = useState("")
  const [appStartDate, setAppStartDate] = useState(null)
  const [appEndDate, setAppEndDate] = useState(null)
  const [futureDays, setFutureDays] = useState(30)
  const [futurePredictions, setFuturePredictions] = useState(null)
  const [priceCurrency, setPriceCurrency] = useState("USD")
  const [sourceCurrency, setSourceCurrency] = useState("USD")
  const [isCurrencyPairInverted, setIsCurrencyPairInverted] = useState(false)
  const [activeView, setActiveView] = useState("stock")
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState("en")
  const { t } = useTranslation()
  const currencyPair = getCurrencyPair(ticker)
  const displayedPair = currencyPair
    ? (isCurrencyPairInverted ? `${currencyPair.quote}/${currencyPair.base}` : `${currencyPair.base}/${currencyPair.quote}`)
    : null
  const alternatePair = currencyPair
    ? (isCurrencyPairInverted ? `${currencyPair.base}/${currencyPair.quote}` : `${currencyPair.quote}/${currencyPair.base}`)
    : null
  const displayedCurrency = currencyPair && isCurrencyPairInverted ? currencyPair.base : priceCurrency
  const displayedData = currencyPair && isCurrencyPairInverted ? invertCurrencySeries(data) : data
  const displayedRegression = currencyPair && isCurrencyPairInverted ? invertCurrencySeries(regressionData) : regressionData
  const displayedFuturePredictions = currencyPair && isCurrencyPairInverted ? invertCurrencySeries(futurePredictions) : futurePredictions

  // AbortController to cancel previous API calls
  const abortControllerRef = useRef(null)

  // Unified data fetching function
  const fetchData = useCallback(async ({
    ticker: requestedTicker,
    modelType: requestedModelType,
    appStartDate: requestedStartDate,
    appEndDate: requestedEndDate,
    futureDays: requestedFutureDays,
  }) => {
    // Cancel any previous API call
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // Create new AbortController for this request
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)

    const url = apiUrl("/api/get-data", {
      ticker: requestedTicker,
      regression: true,
      future_days: requestedFutureDays,
      model: requestedModelType,
      start_date: requestedStartDate,
      end_date: requestedEndDate,
    })

    try {
      const response = await fetch(url, {
        method: "GET",
        mode: "cors",
        credentials: "include",
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const responseData = await response.json()

      if (abortControllerRef.current !== controller) return

      const hasPriceData = responseData.prices && Object.keys(responseData.prices).length > 0

      setData(hasPriceData ? responseData.prices : null)
      setRegressionData(responseData.regression)
      setFuturePredictions(responseData.future_predictions)
      setCompanyName(responseData.companyName)
      setFormula(responseData.formula)
      setPriceCurrency(responseData.price_currency || "USD")
      setSourceCurrency(responseData.source_currency || responseData.price_currency || "USD")
      setShowChart(hasPriceData)
    } catch (error) {
      if (abortControllerRef.current !== controller) return

      if (error.name !== "AbortError") {
        setError(error.message)
      }
    } finally {
      if (abortControllerRef.current === controller) {
        setLoading(false)
        abortControllerRef.current = null
      }
    }
  }, [])

  // useEffect for debounced data fetching
  useEffect(() => {
    if (activeView !== "stock" || !appStartDate || !appEndDate || !ticker) {
      return undefined
    }

    const requestSnapshot = {
      ticker,
      modelType,
      appStartDate,
      appEndDate,
      futureDays,
    }

    const debounceTimeout = setTimeout(() => {
      fetchData(requestSnapshot)
    }, STOCK_FETCH_DEBOUNCE_MS)

    return () => {
      clearTimeout(debounceTimeout)
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [activeView, appStartDate, appEndDate, fetchData, futureDays, modelType, ticker])

  // Initial date setup
  useEffect(() => {
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    const threeMonthsAgo = new Date(yesterday)
    threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3)

    const formatDate = (date) => date.toISOString().split("T")[0]

    setAppStartDate(formatDate(threeMonthsAgo))
    setAppEndDate(formatDate(yesterday))
  }, [])

  const handleDateRangeChange = (newStartDate, newEndDate) => {
    setAppStartDate(newStartDate)
    setAppEndDate(newEndDate)
  }

  const handleTickerChange = (newTicker) => {
    setTicker(newTicker)
    setIsCurrencyPairInverted(false)
  }

  const handleFutureDaysChange = (days) => {
    setFutureDays(days)
  }

  // Cleanup function
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const heartbeat = async () => {
      const job = readOptimizerJob()
      if (!isRunningOptimizerJob(job)) return

      try {
        const response = await fetch(apiUrl(`/api/optimization-jobs/${encodeURIComponent(job.requestId)}`), {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        })

        if (cancelled) return
        if (response.status === 404) {
          clearOptimizerJob()
          return
        }
        if (!response.ok) return

        const status = await response.json()
        writeOptimizerJob({
          requestId: status.request_id || job.requestId,
          portfolioId: status.portfolio_id || job.portfolioId,
          status: status.status || job.status,
          startedAt: job.startedAt,
          updatedAt: new Date().toISOString(),
        })
      } catch {
        // A heartbeat miss should not cancel local recovery state.
      }
    }

    heartbeat()
    const intervalId = window.setInterval(heartbeat, OPTIMIZER_JOB_HEARTBEAT_MS)

    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [])

  return (
    <div className="app-container">
      <a className="skip-link" href="#main-content">
        {t("common.skipToContent", "Skip to content")}
      </a>
      <Selector
        activeView={activeView}
        onViewChange={setActiveView}
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
      />
      <LanguageSelector
        isOpen={isSidebarOpen}
        selectedLanguage={selectedLanguage}
        onLanguageChange={setSelectedLanguage}
      />
      <main className="main-content" id="main-content">
        {activeView === "stock" ? (
          <section className="stock-dashboard" aria-labelledby="stock-dashboard-title" aria-busy={loading}>
            <div className="stock-dashboard-header">
              <div className="stock-title-block">
                <span className="page-kicker">{t("stock.kicker", "Market workspace")}</span>
                <h1 id="stock-dashboard-title">{t("stock.workspaceTitle", "Stock analysis")}</h1>
                <p className="stock-page-intro">
                  {t(
                    "stock.workspaceDescription",
                    "Compare price history, trend fit, and model forecasts in one view.",
                  )}
                </p>
              </div>
              <dl className="stock-context-strip" aria-label={t("stock.selectionSummary", "Current analysis settings")}>
                <div>
                  <dt>{t("stock.symbol", "Symbol")}</dt>
                  <dd>{ticker}</dd>
                </div>
                <div>
                  <dt>{t("stock.model", "Model")}</dt>
                  <dd>{modelType}</dd>
                </div>
                <div>
                  <dt>{t("stock.forecast", "Forecast")}</dt>
                  <dd>{t("stock.dayCount", "{{count}} days", { count: futureDays })}</dd>
                </div>
              </dl>
            </div>

            <section className="stock-workbench" aria-labelledby="stock-workbench-title">
              <header className="stock-workbench-header">
                <div>
                  <h2 id="stock-workbench-title">{t("stock.configure", "Configure analysis")}</h2>
                  <p>
                    {t(
                      "stock.configureDescription",
                      "Choose a security, historical window, and forecast horizon.",
                    )}
                  </p>
                </div>
                <p className="stock-refresh-state" role="status" aria-live="polite">
                  {loading
                    ? t("stock.updating", "Updating market data")
                    : t("stock.autoUpdate", "Charts update automatically")}
                </p>
              </header>

              <div className="controls-container">
                <section className="stock-control-group stock-control-group-asset" aria-labelledby="stock-asset-title">
                  <header className="stock-control-group-header">
                    <h3 id="stock-asset-title">{t("stock.assetAndModel", "Asset and model")}</h3>
                  </header>
                  <div className="control-column">
                    <TickerInput onTickerChange={handleTickerChange} initialTicker="AAPL" />
                    <ModelSelector
                      onModelChange={setModelType}
                      initialModel={modelType}
                      startDate={appStartDate}
                      endDate={appEndDate}
                    />
                  </div>
                </section>

                <section className="stock-control-group stock-control-group-window" aria-labelledby="stock-window-title">
                  <header className="stock-control-group-header">
                    <h3 id="stock-window-title">{t("stock.historicalWindow", "Historical window")}</h3>
                  </header>
                  <DateInput onDateRangeChange={handleDateRangeChange} notifyInitial={false} inputIdPrefix="stock-date" />
                </section>

                <section className="stock-control-group stock-control-group-forecast" aria-labelledby="stock-forecast-title">
                  <header className="stock-control-group-header">
                    <h3 id="stock-forecast-title">{t("stock.forecastSetup", "Forecast horizon")}</h3>
                  </header>
                  <FutureDateInput onFutureDaysChange={handleFutureDaysChange} initialDays={futureDays} />
                  <p className="stock-control-help">
                    {t(
                      "stock.forecastDescription",
                      "Forecasts are estimates from the selected model, not investment advice.",
                    )}
                  </p>
                </section>
              </div>
            </section>

            {loading && <StockChartsSkeleton />}

            {!loading && error && (
              <section className="error stock-error-state" role="alert">
                <p className="stock-error-title">{t("stock.errorTitle", "Market data is unavailable")}</p>
                <p>{t("stock.errorDescription", "Check the symbol and date range, then change a field to try again.")}</p>
                <code>{error}</code>
              </section>
            )}

            {!loading && showChart && data && (
              <section className="stock-results" aria-label={t("regression.data")}>
                <header className="stock-results-header">
                  <div>
                    <p>{t("stock.results", "Analysis results")}</p>
                    <h2>
                      {companyName} <span>({ticker})</span>
                    </h2>
                  </div>
                  <div className="stock-result-details">
                    <dl className="stock-result-meta">
                      <div>
                        <dt>{t("stock.dataWindow", "Data window")}</dt>
                        <dd>{appStartDate} → {appEndDate}</dd>
                      </div>
                      <div>
                        <dt>{currencyPair ? t("stock.rateView", "Rate view") : t("stock.displayCurrency", "Display currency")}</dt>
                        <dd>
                          {currencyPair
                            ? `${displayedPair} · ${displayedCurrency}`
                            : sourceCurrency !== priceCurrency
                              ? `${sourceCurrency} → ${priceCurrency}`
                              : priceCurrency}
                        </dd>
                      </div>
                    </dl>
                    {currencyPair && (
                      <button
                        type="button"
                        className="stock-currency-toggle optimizer-secondary-button manager-display-toggle-button is-compact"
                        onClick={() => setIsCurrencyPairInverted((current) => !current)}
                      >
                        {t("stock.showCurrencyPair", "Show {{pair}}", { pair: alternatePair })}
                      </button>
                    )}
                  </div>
                </header>

                <div className="stock-chart-grid">
                  <div className="chart-wrapper chart-wrapper-price">
                    <StockChart data={displayedData} ticker={ticker} priceCurrency={displayedCurrency} />
                  </div>
                  <div className="chart-wrapper chart-wrapper-regression">
                    <RegressionChart data={displayedData} regression={displayedRegression} ticker={ticker} formula={formula} priceCurrency={displayedCurrency} />
                  </div>
                  {displayedFuturePredictions && Object.keys(displayedFuturePredictions).length > 0 && (
                    <div className="chart-wrapper chart-wrapper-forecast">
                      <FutureChart data={displayedFuturePredictions} historicalData={displayedData} ticker={ticker} priceCurrency={displayedCurrency} />
                    </div>
                  )}
                </div>
              </section>
            )}

            {!loading && !error && !showChart && (
              <section className="empty-state stock-empty-state" aria-live="polite">
                <p className="empty-state-title">{t("stock.emptyTitle", "Market data is pending")}</p>
                <p>{t("stock.emptyDescription", "The selected symbol and date window will appear here when data returns.")}</p>
              </section>
            )}
          </section>
        ) : activeView === "hedge" ? (
          <HedgeAnalysis />
        ) : activeView === "financial" ? (
          <FinancialStatement />
        ) : activeView === "optimizer" ? (
          <Optimizer />
        ) : activeView === "benchmark" ? (
          <PortfolioBenchmark />
        ) : activeView === "manager" ? (
          <PortfolioManager />
        ) : null
        }
      </main>
    </div>
  )
}

export default function App() {
  return (
    <I18nextProvider i18n={i18n}>
      <AppContent />
    </I18nextProvider>
  )
}
