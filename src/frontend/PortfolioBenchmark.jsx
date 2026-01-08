import { useState, useRef } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"
import DateInput from "./DateInput.jsx"
import BenchmarkChart from "./BenchmarkChart.jsx"
import BenchmarkResultsTable from "./BenchmarkResultsTable.jsx"

const PortfolioBenchmark = () => {
  const { t } = useTranslation()
  const [portfolio, setPortfolio] = useState(null)
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
        setError(null)
      } catch (err) {
        setError(err.message || t("benchmark.uploadError"))
        setPortfolio(null)
      }
    }
    reader.onerror = () => {
      setError(t("benchmark.readError"))
      setPortfolio(null)
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
      const response = await axios.post("http://localhost:5000/api/benchmark-portfolio", {
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

  return (
    <div className="optimizer-container">
      <div className="optimizer-header">
        <h2 className="page-header">{t("benchmark.title")}</h2>
      </div>

      <form className="optimizer-form" onSubmit={handleSubmit}>
        {/* Portfolio Upload */}
        <div className="optimizer-form-group">
          <label className="optimizer-label">{t("benchmark.uploadPortfolio")}</label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            onChange={handleFileUpload}
            style={{ display: "none" }}
          />
          <button
            type="button"
            onClick={triggerFileUpload}
            className="optimizer-input optimizer-file-button"
          >
            {portfolio
              ? `✓ ${portfolio.portfolio_id || t("benchmark.portfolioLoaded")}`
              : t("benchmark.chooseFile")}
          </button>
        </div>

        {/* Budget Input */}
        <div className="optimizer-form-group">
          <label className="optimizer-label">{t("benchmark.budget")}</label>
          <input
            type="number"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            placeholder="10000"
            className="optimizer-input"
            step="0.01"
            min="0"
          />
        </div>

        {/* Date Range */}
        <div className="optimizer-form-group">
          <DateInput onDateRangeChange={handleDateRangeChange} />
        </div>

        {/* Risk-Free Rate */}
        <div className="optimizer-form-group">
          <label className="optimizer-label">{t("benchmark.riskFreeRate")}</label>
          <input
            type="number"
            value={riskFreeRate}
            onChange={(e) => setRiskFreeRate(e.target.value)}
            placeholder="4"
            className="optimizer-input"
            step="0.01"
            min="0"
            max="100"
          />
        </div>

        {/* Submit Button */}
        <div style={{ display: "flex", justifyContent: "center", width: "100%" }}>
          <button
            type="submit"
            className="optimizer-submit-button"
            disabled={loading || !portfolio || !budget || !startDate || !endDate}
          >
            {loading ? t("common.loading") : t("benchmark.analyze")}
          </button>
        </div>
      </form>

      {/* Error Display */}
      {error && (
        <div className="optimizer-error">
          <p>{error}</p>
        </div>
      )}

      {/* Results Display */}
      {benchmarkData && !loading && (
        <div className="benchmark-results">
          <h2 className="optimizer-section-title">{t("benchmark.resultsTitle")}</h2>

          {/* Chart */}
          <div className="charts-container">
            <div className="chart-wrapper">
              <BenchmarkChart
                portfolioData={benchmarkData.portfolio_timeline}
                sp500Data={benchmarkData.sp500_timeline}
                riskfreeData={benchmarkData.riskfree_timeline}
              />
            </div>
          </div>

          {/* Summary Table */}
          <BenchmarkResultsTable summary={benchmarkData.summary} />
        </div>
      )}
    </div>
  )
}

export default PortfolioBenchmark
