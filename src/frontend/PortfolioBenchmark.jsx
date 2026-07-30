import { useState, useRef } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"
import DateInput from "./DateInput.jsx"
import BenchmarkChart from "./BenchmarkChart.jsx"
import BenchmarkResultsTable from "./BenchmarkResultsTable.jsx"
import { apiUrl } from "./apiClient.js"
import { BenchmarkSkeleton } from "./SkeletonScreens.jsx"

const PortfolioBenchmark = () => {
  const { t } = useTranslation()
  const [portfolio, setPortfolio] = useState(null)
  const [portfolioFileName, setPortfolioFileName] = useState("")
  const [budget, setBudget] = useState("")
  const [riskFreeRate, setRiskFreeRate] = useState("4")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [benchmarkData, setBenchmarkData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)

  // Handle portfolio JSON file upload
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target.result)

        // Validate portfolio structure
        if (!parsed || typeof parsed !== "object") {
          throw new Error(t("benchmark.invalidFile"))
        }
        if (!parsed.weights || !parsed.prices) {
          throw new Error(t("benchmark.missingFields"))
        }

        setPortfolio(parsed)
        setPortfolioFileName(file.name)
        setError(null)
      } catch (err) {
        setError(err.message || t("benchmark.uploadError"))
        setPortfolio(null)
        setPortfolioFileName("")
      }
    }
    reader.onerror = () => {
      setError(t("benchmark.readError"))
      setPortfolio(null)
      setPortfolioFileName("")
    }
    reader.readAsText(file)

    // Reset input to allow same file upload again
    e.target.value = ""
  }

  // Trigger file input click
  const triggerFileUpload = () => {
    fileInputRef.current?.click()
  }

  // Handle date range changes from DateInput component
  const handleDateRangeChange = (start, end) => {
    setStartDate(start)
    setEndDate(end)
  }

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault()

    // Validate inputs
    if (!portfolio) {
      setError(t("benchmark.noPortfolio"))
      return
    }
    if (!budget || parseFloat(budget) <= 0) {
      setError(t("benchmark.invalidBudget"))
      return
    }
    if (!startDate || !endDate) {
      setError(t("benchmark.noDateRange"))
      return
    }

    setLoading(true)
    setError(null)

    try {
      const response = await axios.post(apiUrl("/api/benchmark-portfolio"), {
        portfolio_data: portfolio,
        budget: parseFloat(budget),
        start_date: startDate,
        end_date: endDate,
        risk_free_rate: parseFloat(riskFreeRate) / 100, // Convert percentage to decimal
      })

      setBenchmarkData(response.data)
      setLoading(false)
    } catch (err) {
      setError(err.response?.data?.error || t("benchmark.apiError"))
      setLoading(false)
      setBenchmarkData(null)
    }
  }

  const portfolioName =
    portfolio?.portfolio_id || portfolioFileName || t("benchmark.portfolioLoaded")
  const assetCount = portfolio?.weights ? Object.keys(portfolio.weights).length : 0
  const isReady = Boolean(portfolio && budget && startDate && endDate)

  return (
    <section
      className="benchmark-page"
      aria-busy={loading}
      aria-labelledby="benchmark-page-title"
    >
      <header className="benchmark-hero" aria-labelledby="benchmark-page-title">
        <div className="benchmark-hero-copy">
          <span className="page-kicker">{t("benchmark.kicker")}</span>
          <h1 id="benchmark-page-title">{t("benchmark.title")}</h1>
          <p>{t("benchmark.subtitle")}</p>
        </div>
        <dl className="benchmark-comparison-set" aria-label={t("benchmark.comparisonSet")}>
          <div>
            <dt>{t("benchmark.primarySeries")}</dt>
            <dd>{t("benchmark.portfolio")}</dd>
          </div>
          <div>
            <dt>{t("benchmark.marketReference")}</dt>
            <dd>{t("benchmark.sp500")}</dd>
          </div>
          <div>
            <dt>{t("benchmark.baseline")}</dt>
            <dd>{t("benchmark.riskFree")}</dd>
          </div>
        </dl>
      </header>

      <form className="benchmark-workbench" onSubmit={handleSubmit}>
        <section className="benchmark-source-panel" aria-labelledby="benchmark-source-title">
          <div className="benchmark-panel-heading">
            <h2 id="benchmark-source-title">{t("benchmark.sourceTitle")}</h2>
            <p>{t("benchmark.sourceDescription")}</p>
          </div>
          <input
            ref={fileInputRef}
            id="benchmark-portfolio-file"
            type="file"
            accept=".json,application/json"
            onChange={handleFileUpload}
            className="hidden-file-input"
          />
          <button
            type="button"
            onClick={triggerFileUpload}
            className={`benchmark-file-drop${portfolio ? " is-loaded" : ""}`}
            aria-describedby="benchmark-file-help"
          >
            <span>{portfolio ? t("benchmark.portfolioLoaded") : t("benchmark.uploadPortfolio")}</span>
            <strong>{portfolio ? portfolioName : t("benchmark.chooseFile")}</strong>
            <small id="benchmark-file-help">
              {portfolio
                ? t("benchmark.assetsReady", { count: assetCount })
                : t("benchmark.fileFormat")}
            </small>
          </button>
          <div className="benchmark-source-note">
            <span>{t("benchmark.sourceNoteLabel")}</span>
            <p>{t("benchmark.sourceNote")}</p>
          </div>
        </section>

        <section className="benchmark-parameters-panel" aria-labelledby="benchmark-parameters-title">
          <div className="benchmark-panel-heading">
            <h2 id="benchmark-parameters-title">{t("benchmark.parametersTitle")}</h2>
            <p>{t("benchmark.parametersDescription")}</p>
          </div>

          <div className="benchmark-fields">
            <div className="benchmark-field">
              <label htmlFor="benchmark-budget">{t("benchmark.budget")}</label>
              <input
                id="benchmark-budget"
                type="number"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder="10000"
                step="0.01"
                min="0"
                inputMode="decimal"
                aria-describedby="benchmark-budget-help"
              />
              <small id="benchmark-budget-help">{t("benchmark.budgetHint")}</small>
            </div>

            <div className="benchmark-field">
              <label htmlFor="benchmark-risk-free-rate">{t("benchmark.riskFreeRate")}</label>
              <input
                id="benchmark-risk-free-rate"
                type="number"
                value={riskFreeRate}
                onChange={(e) => setRiskFreeRate(e.target.value)}
                placeholder="4"
                step="0.01"
                min="0"
                max="100"
                inputMode="decimal"
                aria-describedby="benchmark-rate-help"
              />
              <small id="benchmark-rate-help">{t("benchmark.riskFreeHint")}</small>
            </div>

            <div className="benchmark-date-field">
              <DateInput onDateRangeChange={handleDateRangeChange} inputIdPrefix="benchmark-date" />
            </div>
          </div>

          <footer className="benchmark-submit-panel">
            <div>
              <strong>{isReady ? t("benchmark.readyTitle") : t("benchmark.notReadyTitle")}</strong>
              <span>{isReady ? t("benchmark.readyHint") : t("benchmark.notReadyHint")}</span>
            </div>
            <button
              type="submit"
              className="benchmark-submit-button"
              disabled={loading || !isReady}
            >
              {loading ? t("common.loading") : t("benchmark.analyze")}
            </button>
          </footer>
        </section>
      </form>

      {error && (
        <div className="benchmark-error" role="alert">
          <strong>{t("benchmark.errorTitle")}</strong>
          <p>{error}</p>
        </div>
      )}

      {loading && <BenchmarkSkeleton />}

      {benchmarkData && !loading && (
        <section className="benchmark-results" aria-labelledby="benchmark-results-title">
          <div className="benchmark-results-heading">
            <span>{t("benchmark.resultsLabel")}</span>
            <h2 id="benchmark-results-title">{t("benchmark.resultsTitle")}</h2>
            <p>{t("benchmark.resultsDescription")}</p>
          </div>

          <div className="benchmark-chart-panel">
            <div className="benchmark-chart-heading">
              <h3>{t("benchmark.chartTitle")}</h3>
              <p>{t("benchmark.chartDescription")}</p>
            </div>
            <div className="benchmark-chart-frame">
              <BenchmarkChart
                portfolioData={benchmarkData.portfolio_timeline}
                sp500Data={benchmarkData.sp500_timeline}
                riskfreeData={benchmarkData.riskfree_timeline}
              />
            </div>
          </div>

          <BenchmarkResultsTable summary={benchmarkData.summary} />
        </section>
      )}
    </section>
  )
}

export default PortfolioBenchmark
