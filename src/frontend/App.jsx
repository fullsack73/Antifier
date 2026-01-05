"use client"

import { useState, useEffect, useRef } from "react"
import { I18nextProvider, useTranslation } from "react-i18next"
import i18n from "./config/i18n"
import StockChart from "./StockChart.jsx"
import DateInput from "./DateInput.jsx"
import TickerInput from "./TickerInput.jsx"
import RegressionChart from "./RegressionChart.jsx"
import Selector from "./Selector.jsx"
import HedgeAnalysis from "./Hedge.jsx"
import LanguageSelector from "./LanguageSelector.jsx"
import FutureDateInput from "./FutureDateInput.jsx"
import FutureChart from "./FutureChart.jsx"
import FinancialStatement from "./FinancialStatement.jsx"
import Optimizer from "./Optimizer.jsx"
import PortfolioBenchmark from "./PortfolioBenchmark.jsx"
import "./App.css"

function AppContent() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [ticker, setTicker] = useState("AAPL")
  const [companyName, setCompanyName] = useState("Apple Inc.")
  const [showChart, setShowChart] = useState(false)
  const [regressionData, setRegressionData] = useState(null)
  const [formula, setFormula] = useState("")
  const [appStartDate, setAppStartDate] = useState(null)
  const [appEndDate, setAppEndDate] = useState(null)
  const [futureDays, setFutureDays] = useState(30)
  const [futurePredictions, setFuturePredictions] = useState(null)
  const [activeView, setActiveView] = useState("stock")
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState("en")
  const { t } = useTranslation()

  // AbortController to cancel previous API calls
  const abortControllerRef = useRef(null)

  // Unified data fetching function
  const fetchData = () => {
    // Cancel any previous API call
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // Create new AbortController for this request
    abortControllerRef.current = new AbortController()

    setLoading(true)
    setError(null)

    let url = `/api/get-data?ticker=${ticker}&regression=true&future_days=${futureDays}`
    if (appStartDate && appEndDate) {
      url += `&start_date=${appStartDate}&end_date=${appEndDate}`
    }

    fetch(url, {
      method: "GET",
      mode: "cors",
      credentials: "include",
      signal: abortControllerRef.current.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        return response.json()
      })
      .then((responseData) => {
        setData(responseData.prices)
        setRegressionData(responseData.regression)
        setFuturePredictions(responseData.future_predictions)
        setCompanyName(responseData.companyName)
        setFormula(responseData.formula)
        setLoading(false)
        setShowChart(true)
      })
      .catch((error) => {
        if (error.name === "AbortError") {
          console.log("🚫 API call was cancelled")
          return
        }
        setError(error.message)
        setLoading(false)
      })
  }

  // useEffect for debounced data fetching
  useEffect(() => {
    const debounceTimeout = setTimeout(() => {
      if (appStartDate && appEndDate && ticker) {
        fetchData()
      }
    }, 800) // 800ms debounce delay

    return () => clearTimeout(debounceTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appStartDate, appEndDate, ticker, futureDays])

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

  return (
    <div className="app-container">
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
      <main className="main-content">
        {activeView === "stock" ? (
          <>
            <h1>{t("regression.title")}</h1>
            <div className="controls-container">
              <TickerInput onTickerChange={handleTickerChange} initialTicker="AAPL" />
              <DateInput onDateRangeChange={handleDateRangeChange} />
              <FutureDateInput onFutureDaysChange={handleFutureDaysChange} initialDays={futureDays} />
            </div>

            {error && (
              <p className="error">
                {t("common.error")}: {error}
              </p>
            )}

            {showChart && data && (
              <>
                <h2>
                  {companyName} ({ticker})
                </h2>
                <div className="charts-container">
                  <div className="chart-wrapper">
                    <StockChart data={data} ticker={ticker} />
                  </div>
                  <div className="chart-wrapper">
                    <RegressionChart data={data} regression={regressionData} ticker={ticker} formula={formula} />
                  </div>
                </div>
                {futurePredictions && (
                  <div className="charts-container">
                    <div className="chart-wrapper">
                      <FutureChart data={futurePredictions} ticker={ticker} />
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        ) : activeView === "hedge" ? (
          <HedgeAnalysis />
        ) : activeView === "financial" ? (
          <FinancialStatement />
        ) : activeView === "optimizer" ? (
          <Optimizer />
        ) : activeView === "benchmark" ? (
          <PortfolioBenchmark />
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
