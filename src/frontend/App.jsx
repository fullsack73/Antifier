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
import "./App.css"

const STOCK_FETCH_DEBOUNCE_MS = 1800
const OPTIMIZER_JOB_HEARTBEAT_MS = 30000

function AppContent() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
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
  const [activeView, setActiveView] = useState("stock")
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState("en")
  const { t } = useTranslation()

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

      setData(responseData.prices)
      setRegressionData(responseData.regression)
      setFuturePredictions(responseData.future_predictions)
      setCompanyName(responseData.companyName)
      setFormula(responseData.formula)
      setPriceCurrency(responseData.price_currency || "USD")
      setSourceCurrency(responseData.source_currency || responseData.price_currency || "USD")
      setShowChart(true)
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
          <section className="stock-dashboard" aria-labelledby="stock-dashboard-title">
            <div className="stock-dashboard-header">
              <div>
                <span className="page-kicker">{t("stock.title")}</span>
                <h1 id="stock-dashboard-title">{t("regression.title")}</h1>
              </div>
              <div className="stock-context-strip" aria-label={t("stock.selectionSummary", "Current analysis settings")}>
                <span>{ticker}</span>
                <span>{modelType}</span>
                <span>{futureDays}D</span>
              </div>
            </div>
            <div className="controls-container">
              <div className="control-column">
                <TickerInput onTickerChange={handleTickerChange} initialTicker="AAPL" />
                <ModelSelector onModelChange={setModelType} initialModel={modelType} />
              </div>
              <DateInput onDateRangeChange={handleDateRangeChange} notifyInitial={false} inputIdPrefix="stock-date" />
              <FutureDateInput onFutureDaysChange={handleFutureDaysChange} initialDays={futureDays} />
            </div>

            {loading && <StockChartsSkeleton />}

            {!loading && error && (
              <p className="error">
                {t("common.error")}: {error}
              </p>
            )}

            {!loading && showChart && data && (
              <section className="stock-results" aria-label={t("regression.data")}>
                <h2>
                  {companyName} ({ticker})
                  {sourceCurrency !== priceCurrency ? ` ${sourceCurrency} -> ${priceCurrency}` : ""}
                </h2>
                <div className="charts-container">
                  <div className="chart-wrapper">
                    <StockChart data={data} ticker={ticker} priceCurrency={priceCurrency} />
                  </div>
                  <div className="chart-wrapper">
                    <RegressionChart data={data} regression={regressionData} ticker={ticker} formula={formula} priceCurrency={priceCurrency} />
                  </div>
                </div>
                {futurePredictions && Object.keys(futurePredictions).length > 0 && (
                  <div className="charts-container">
                    <div className="chart-wrapper">
                      <FutureChart data={futurePredictions} historicalData={data} ticker={ticker} priceCurrency={priceCurrency} />
                    </div>
                  </div>
                )}
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
