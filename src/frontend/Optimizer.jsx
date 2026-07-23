"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import axios from "axios"
import { fetchSecurityNames, formatSecurityDisplay, getSecurityDisplayName } from "./securityDisplay"
import { apiUrl } from "./apiClient.js"
import { clearOptimizerJob, readOptimizerJob, writeOptimizerJob } from "./optimizerJobStorage.js"
import { OptimizerSkeleton } from "./SkeletonScreens.jsx"

const TERMINAL_JOB_STATUSES = new Set(["completed", "failed", "cancelled"])

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
  const [progress, setProgress] = useState(null)
  const [activeJob, setActiveJob] = useState(null)
  const [cancelRequested, setCancelRequested] = useState(false)
  const portfolioFileInputRef = useRef(null)
  const csvFileInputRef = useRef(null)
  const eventSourceRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const submittedRequestIdRef = useRef(null)
  const cancellingRequestIdRef = useRef(null)

  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (!file) return

    setUploadError(null)
    setUploadFileName(file.name)

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setUploadError(t("optimizer.csvOnly", "Only .csv files are accepted."))
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
        setUploadError(t("optimizer.noValidTickers", "No valid ticker symbols found in the file."))
        setCustomTickers([])
      } else {
        setCustomTickers(tickers)
      }
    }
    reader.onerror = () => {
      setUploadError(t("optimizer.readCsvError", "Failed to read the file."))
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
          throw new Error(t("optimizer.invalidPortfolioFile", "Invalid portfolio file: missing weights"))
        }
        setOptimizedPortfolio(parsed)
        setAllocation(null)
        setError(null)
      } catch (uploadError) {
        setError(uploadError.message || t("optimizer.loadPortfolioError", "Failed to load portfolio file"))
      }
    }
    reader.onerror = () => setError(t("optimizer.readPortfolioError", "Failed to read portfolio file"))
    reader.readAsText(file)

    // Reset input value to allow uploading the same file again if needed
    event.target.value = ""
  }

  const generateRequestId = () => `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

  const closeProgressStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }, [])

  const persistJobRecord = useCallback((record) => {
    const savedRecord = writeOptimizerJob(record)
    setActiveJob(savedRecord || record)
    return savedRecord || record
  }, [])

  const forgetJobRecord = useCallback(() => {
    clearOptimizerJob()
    setActiveJob(null)
  }, [])

  const jobRecordFromStatus = useCallback((status, fallback = {}) => ({
    requestId: status.request_id || fallback.requestId,
    portfolioId: status.portfolio_id || fallback.portfolioId || status.request_id || fallback.requestId,
    status: status.status || fallback.status || "running",
    startedAt: fallback.startedAt || new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }), [])

  const applyCompletedJob = useCallback((status, fallback = {}) => {
    closeProgressStream()
    if ((status.request_id || fallback.requestId) === cancellingRequestIdRef.current) {
      cancellingRequestIdRef.current = null
    }
    setProgress({
      percentage: 100,
      message: status.message || t("optimizer.complete", "Optimization complete!"),
    })
    if (status.result) {
      setOptimizedPortfolio(status.result)
    }
    setAllocation(null)
    setError(null)
    setErrorDetails(null)
    setLoading(false)
    setCancelRequested(false)
    persistJobRecord(jobRecordFromStatus({ ...status, status: "completed" }, fallback))
  }, [closeProgressStream, jobRecordFromStatus, persistJobRecord, t])

  const applyTerminalJob = useCallback((status, fallback = {}) => {
    closeProgressStream()
    const statusText = status.status === "cancelled"
      ? t("optimizer.cancelled", "Optimization cancelled")
      : t("optimizer.failed", "Optimization failed")
    setError(status.error || status.message || statusText)
    setErrorDetails(null)
    setLoading(false)
    setCancelRequested(false)
    setOptimizedPortfolio(null)
    setAllocation(null)
    setProgress({
      percentage: status.progress ?? fallback.progress ?? 0,
      message: status.message || statusText,
    })
    forgetJobRecord()
  }, [closeProgressStream, forgetJobRecord, t])

  const fetchJobStatus = useCallback(async (requestId) => {
    const response = await fetch(apiUrl(`/api/optimization-jobs/${encodeURIComponent(requestId)}`), {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    })
    if (response.status === 404) return null
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.error || t("optimizer.statusError", "Failed to check optimization status"))
    }
    return response.json()
  }, [t])

  const loadPersistedPortfolio = useCallback(async (portfolioId, fallback = {}) => {
    if (!portfolioId) return false

    const response = await fetch(apiUrl(`/api/portfolio-results/${encodeURIComponent(portfolioId)}`), {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    })
    if (!response.ok) return false

    const result = await response.json()
    applyCompletedJob({
      request_id: fallback.requestId,
      portfolio_id: portfolioId,
      status: "completed",
      progress: 100,
      message: t("optimizer.complete", "Optimization complete!"),
      result,
    }, fallback)
    return true
  }, [applyCompletedJob, t])

  const handleJobStatus = useCallback(async (status, fallback = {}) => {
    const statusRequestId = status?.request_id || fallback.requestId
    if (status?.status === "running" && cancellingRequestIdRef.current === statusRequestId) {
      return
    }

    if (!status) {
      const loaded = await loadPersistedPortfolio(fallback.portfolioId, fallback)
      if (!loaded) {
        forgetJobRecord()
      }
      return
    }

    if (status.status === "completed") {
      applyCompletedJob(status, fallback)
      return
    }
    if (status.status === "failed" || status.status === "cancelled") {
      applyTerminalJob(status, fallback)
      return
    }

    const record = persistJobRecord(jobRecordFromStatus(status, fallback))
    setLoading(true)
    setCancelRequested(false)
    setProgress({
      percentage: status.progress ?? 0,
      message: status.message || t("optimizer.backgroundRunning", "Optimization is running in the background."),
    })
    setActiveJob(record)
  }, [
    applyCompletedJob,
    applyTerminalJob,
    forgetJobRecord,
    jobRecordFromStatus,
    loadPersistedPortfolio,
    persistJobRecord,
    t,
  ])

  const attachProgressStream = useCallback((requestId, fallback = {}) => {
    closeProgressStream()
    if (!requestId) return

    const eventSource = new EventSource(apiUrl(`/api/progress-stream/${encodeURIComponent(requestId)}`))
    eventSourceRef.current = eventSource

    eventSource.onmessage = () => {
      // Ping/keep-alive, ignore.
    }

    eventSource.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data)
      persistJobRecord(jobRecordFromStatus(data, fallback))
      setLoading(true)
      setProgress({
        percentage: data.progress ?? 0,
        message: data.message || t("optimizer.backgroundRunning", "Optimization is running in the background."),
      })
    })

    eventSource.addEventListener("complete", (e) => {
      const data = JSON.parse(e.data)
      applyCompletedJob(data, fallback)
    })

    eventSource.addEventListener("cancelled", (e) => {
      const data = JSON.parse(e.data)
      applyTerminalJob(data, fallback)
    })

    eventSource.addEventListener("error", (e) => {
      if (e.data) {
        const data = JSON.parse(e.data)
        applyTerminalJob(data, fallback)
        return
      }

      eventSource.close()
      eventSourceRef.current = null
      setProgress(prev => ({
        percentage: prev?.percentage ?? 0,
        message: t("optimizer.reconnecting", "Progress connection lost. Reconnecting..."),
      }))
      reconnectTimeoutRef.current = window.setTimeout(async () => {
        try {
          const status = await fetchJobStatus(requestId)
          await handleJobStatus(status, fallback)
          if (status?.status === "running") {
            attachProgressStream(requestId, fallback)
          }
        } catch (statusError) {
          if (import.meta.env.DEV) {
            console.error(statusError)
          }
        }
      }, 2000)
    })
  }, [
    applyCompletedJob,
    applyTerminalJob,
    closeProgressStream,
    fetchJobStatus,
    handleJobStatus,
    jobRecordFromStatus,
    persistJobRecord,
    t,
  ])

  useEffect(() => {
    let cancelled = false

    const restoreJob = async () => {
      const storedJob = readOptimizerJob()
      if (!storedJob?.requestId) return
      if (submittedRequestIdRef.current === storedJob.requestId) return

      try {
        const status = await fetchJobStatus(storedJob.requestId)
        if (cancelled) return
        if (submittedRequestIdRef.current === storedJob.requestId) return
        await handleJobStatus(status, storedJob)
        if (!cancelled && status?.status === "running") {
          attachProgressStream(storedJob.requestId, storedJob)
        }
      } catch (restoreError) {
        if (import.meta.env.DEV) {
          console.error(restoreError)
        }
        if (!cancelled) {
          const loaded = await loadPersistedPortfolio(storedJob.portfolioId, storedJob)
          if (!loaded) {
            forgetJobRecord()
          }
        }
      }
    }

    restoreJob()

    return () => {
      cancelled = true
      closeProgressStream()
    }
  }, [
    attachProgressStream,
    closeProgressStream,
    fetchJobStatus,
    forgetJobRecord,
    handleJobStatus,
    loadPersistedPortfolio,
  ])

  const handleCancelOptimization = async () => {
    const job = activeJob || readOptimizerJob()
    if (!job?.requestId) return

    cancellingRequestIdRef.current = job.requestId
    setCancelRequested(true)
    setProgress(prev => ({
      percentage: prev?.percentage ?? 0,
      message: t("optimizer.cancelRequested", "Cancellation requested..."),
    }))

    try {
      const response = await axios.post(apiUrl(`/api/optimization-jobs/${encodeURIComponent(job.requestId)}/cancel`))
      if (TERMINAL_JOB_STATUSES.has(response.data?.status)) {
        if (response.data.status === "completed") {
          applyCompletedJob(response.data, job)
        } else {
          applyTerminalJob(response.data, job)
        }
      }
    } catch (cancelError) {
      cancellingRequestIdRef.current = null
      setCancelRequested(false)
      setError(cancelError.response?.data?.error || t("optimizer.cancelError", "Failed to cancel optimization"))
    }
  }

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
    closeProgressStream()
    setLoading(true)
    setError(null)
    setErrorDetails(null)
    setOptimizedPortfolio(null)
    setAllocation(null)
    setCancelRequested(false)
    setProgress({ percentage: 0, message: t("common.starting", "Starting...") })

    const requestId = generateRequestId()
    submittedRequestIdRef.current = requestId
    cancellingRequestIdRef.current = null
    const portfolioId = requestId
    const startedAt = new Date().toISOString()
    const jobRecord = persistJobRecord({
      requestId,
      portfolioId,
      status: "running",
      startedAt,
      updatedAt: startedAt,
    })

    try {
      const payload = {
        start_date: startDate,
        end_date: endDate,
        risk_free_rate: Number.parseFloat(riskFreeRate) / 100,
        target_return: targetReturn ? Number.parseFloat(targetReturn) / 100 : null,
        risk_tolerance: riskTolerance ? Number.parseFloat(riskTolerance) / 100 : null,
        request_id: requestId,
        portfolio_id: portfolioId,
        persist_result: true,
        load_if_available: true,
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

      const response = await axios.post(apiUrl("/api/optimize-portfolio"), payload)
      const status = response.data
      await handleJobStatus(status, jobRecord)
      if (status?.status === "running") {
        attachProgressStream(requestId, jobRecord)
      }

    } catch (err) {
      if (import.meta.env.DEV) {
        console.error(err)
      }
      if (err.response && err.response.data) {
        setError(err.response.data.error || t("optimizer.startError", "An error occurred starting optimization"))
        setErrorDetails(err.response.data.details || null)
      } else {
        setError(t("optimizer.startError", "An error occurred starting optimization"))
        setErrorDetails(err.message)
      }
      setOptimizedPortfolio(null)
      setLoading(false)
      forgetJobRecord()
    }
  }

  const universeSummary = tickerGroup === "CUSTOM"
    ? t("optimizer.customUniverseSummary", "{{count}} custom tickers", { count: customTickers.length })
    : tickerGroup === "DOW"
      ? "Dow Jones"
      : "S&P 500"
  const forecastSummary = {
    LIGHTWEIGHT: t("optimizer.lightweight", "Lightweight Prediction"),
    ARIMA_TRANSFORMER: t("optimizer.ensemble", "ARIMA + Transformer"),
    TRANSFORMER: t("optimizer.transformer", "Transformer"),
  }[forecastMethod]
  const methodSummary = optimizationMethod === "BL"
    ? t("optimizer.blShort", "Black-Litterman")
    : t("optimizer.mptShort", "Classic MPT")
  const constraintSummary = targetReturn
    ? t("optimizer.targetConstraintSummary", "{{value}}% target return", { value: targetReturn })
    : riskTolerance
      ? t("optimizer.riskConstraintSummary", "{{value}}% risk ceiling", { value: riskTolerance })
      : t("optimizer.noCustomConstraint", "No custom constraint")

  return (
    <div className="optimizer-container">
      <header className="optimizer-page-header">
        <div className="page-title-block optimizer-title-block">
          <span className="page-kicker">{t("optimizer.kicker")}</span>
          <h1 className="page-header">{t("optimizer.title")}</h1>
          <p className="optimizer-page-intro">
            {t(
              "optimizer.intro",
              "Build a model-led allocation from a defined universe, historical window, and risk objective.",
            )}
          </p>
        </div>
        <div className="optimizer-context-strip" aria-label={t("optimizer.runContext", "Current run context")}>
          <div>
            <span>{t("optimizer.universe", "Universe")}</span>
            <strong>{universeSummary}</strong>
          </div>
          <div>
            <span>{t("optimizer.forecast", "Forecast")}</span>
            <strong>{forecastSummary}</strong>
          </div>
          <div>
            <span>{t("optimizer.method", "Method")}</span>
            <strong>{methodSummary}</strong>
          </div>
        </div>
      </header>

      <section className="optimizer-workbench" aria-labelledby="optimizer-setup-title">
        <div className="optimizer-workbench-header">
          <div>
            <span className="optimizer-section-eyebrow">{t("optimizer.strategySetup", "Strategy setup")}</span>
            <h2 id="optimizer-setup-title">{t("optimizer.optimizationBrief", "Optimization brief")}</h2>
            <p>{t("optimizer.setupHelp", "Define the investable universe first, then choose how the model should estimate and allocate.")}</p>
          </div>
          <div className="optimizer-actions-row optimizer-actions-row-compact">
            <button className="optimizer-secondary-button" type="button" onClick={triggerPortfolioUpload}>
              <span aria-hidden="true">↥</span>
              {t("optimizer.loadPortfolio", "Load JSON")}
            </button>
            <button className="optimizer-secondary-button" type="button" onClick={() => setShowAdvanced(true)}>
              <span aria-hidden="true">⋯</span>
              {t("optimizer.advancedSettings", "Advanced Settings")}
            </button>
            <input
              type="file"
              accept="application/json"
              ref={portfolioFileInputRef}
              className="hidden-file-input"
              onChange={handlePortfolioUpload}
            />
          </div>
        </div>

        <form onSubmit={handleSubmit} className="optimizer-form">
          <div className="optimizer-form-grid">
            <section className="optimizer-form-section">
              <div className="optimizer-form-section-heading">
                <span>01</span>
                <div>
                  <h3>{t("optimizer.chooseUniverse", "Choose the universe")}</h3>
                  <p>{t("optimizer.chooseUniverseHelp", "Select a market index or upload your own ticker list.")}</p>
                </div>
              </div>
              <div className="optimizer-form-section-fields optimizer-form-section-single">
                <div className="optimizer-form-group">
                  <label htmlFor="tickerGroup">{t("optimizer.tickerGroup")}</label>
                  {tickerGroup === "CUSTOM" && customTickers.length > 0 ? (
                    <button
                      id="tickerGroup"
                      type="button"
                      className="optimizer-select optimizer-select-button"
                      onClick={() => setShowUploadModal(true)}
                    >
                      {uploadFileName} ({customTickers.length})
                    </button>
                  ) : (
                    <select
                      id="tickerGroup"
                      className="optimizer-select"
                      value={tickerGroup}
                      onChange={(e) => {
                        setTickerGroup(e.target.value)
                        if (e.target.value === "CUSTOM") {
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
              </div>
            </section>

            <section className="optimizer-form-section">
              <div className="optimizer-form-section-heading">
                <span>02</span>
                <div>
                  <h3>{t("optimizer.selectModels", "Select the models")}</h3>
                  <p>{t("optimizer.selectModelsHelp", "Pair a return forecast with an allocation framework.")}</p>
                </div>
              </div>
              <div className="optimizer-form-section-fields">
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
              </div>
            </section>

            <section className="optimizer-form-section">
              <div className="optimizer-form-section-heading">
                <span>03</span>
                <div>
                  <h3>{t("optimizer.setHistory", "Set the historical window")}</h3>
                  <p>{t("optimizer.setHistoryHelp", "Choose the period used to estimate return and covariance.")}</p>
                </div>
              </div>
              <div className="optimizer-form-section-fields">
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
              </div>
            </section>

            <section className="optimizer-form-section">
              <div className="optimizer-form-section-heading">
                <span>04</span>
                <div>
                  <h3>{t("optimizer.defineObjective", "Define the objective")}</h3>
                  <p>{t("optimizer.defineObjectiveHelp", "Set the baseline rate and review any optional return or risk constraint.")}</p>
                </div>
              </div>
              <div className="optimizer-objective-layout">
                <div className="optimizer-form-group">
                  <label htmlFor="riskFreeRate">{t("optimizer.riskFreeRate")}</label>
                  <div className="input-with-symbol">
                    <input
                      id="riskFreeRate"
                      className="optimizer-input"
                      type="number"
                      value={riskFreeRate}
                      onChange={(e) => setRiskFreeRate(e.target.value)}
                      placeholder={t("optimizer.riskFreePlaceholder", "e.g., 2")}
                      required
                    />
                  </div>
                </div>
                <button
                  type="button"
                  className="optimizer-constraint-summary"
                  onClick={() => setShowAdvanced(true)}
                >
                  <span>{t("optimizer.optionalConstraint", "Optional constraint")}</span>
                  <strong>{constraintSummary}</strong>
                  <small>{t("optimizer.editConstraint", "Review advanced controls")}</small>
                </button>
              </div>
            </section>
          </div>

          <div className="optimizer-submit-panel">
            <div>
              <span>{t("optimizer.readyLabel", "Ready to run")}</span>
              <p>{t("optimizer.readyHelp", "The optimizer runs as a recoverable background job. Results remain analysis support, not investment advice.")}</p>
            </div>
            <button type="submit" className="optimizer-submit-button" disabled={loading}>
              {loading ? t("common.processing", "Processing...") : t("optimizer.submit")}
            </button>
          </div>

          {showAdvanced && (
            <div className="optimizer-modal-overlay" onClick={() => setShowAdvanced(false)}>
              <div className="optimizer-modal-content optimizer-advanced-modal" onClick={e => e.stopPropagation()}>
                <div className="optimizer-modal-header">
                  <h3 className="optimizer-modal-title">{t("optimizer.advancedSettings", "Advanced Settings")}</h3>
                  <button type="button" className="optimizer-modal-close" onClick={() => setShowAdvanced(false)} aria-label={t("common.close", "Close")}>×</button>
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
                            placeholder={t("optimizer.targetReturnPlaceholder", "e.g., 20")}
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
                            placeholder={t("optimizer.riskTolerancePlaceholder", "e.g., 15")}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="optimizer-advanced-section">
                    <div className="optimizer-advanced-section-title">{t("optimizer.forecastControls", "Forecast Controls")}</div>
                    <div className="optimizer-advanced-grid">
                      <div className="optimizer-form-group">
                        <label htmlFor="forecastHorizon" title={t("optimizer.forecastHorizonTitle", "Number of trading days to forecast into the future. Default is 63 (roughly one quarter).")}>{t("optimizer.forecastHorizon", "Forecast Horizon (Days)")}</label>
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
                        <label htmlFor="minHistory" title={t("optimizer.minHistoryTitle", "Minimum number of historical data points required for a ticker to be included.")}>{t("optimizer.minHistory", "Min. Data History (Days)")}</label>
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
                          <label htmlFor="blTau" title={t("optimizer.blTauTitle", "A scalar indicating the uncertainty of the CAPM prior (0 to 1). Lower values mean higher confidence in the market equilibrium. Standard default is 0.05.")}>{t("optimizer.blTau", "Black-Litterman Tau")}</label>
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
                  <button type="button" className="optimizer-modal-close" onClick={handleCloseUploadModal} aria-label={t("common.close", "Close")}>×</button>
                </div>
                <div className="optimizer-modal-body">
                  <p className="modal-helper-text">
                    {t("optimizer.customTickersHelp", "Upload a .csv file containing ticker symbols (one per line or comma-separated). Header rows like \"Symbol\" or \"Ticker\" are automatically ignored.")}
                  </p>
                  <button
                    type="button"
                    className="optimizer-secondary-button modal-full-width-button"
                    onClick={() => csvFileInputRef.current?.click()}
                  >
                    {uploadFileName ? t("optimizer.changeFile", "Change File") : t("optimizer.chooseCsvFile", "Choose CSV File")}
                  </button>
                  <input
                    type="file"
                    accept=".csv"
                    ref={csvFileInputRef}
                    className="hidden-file-input"
                    onChange={handleFileUpload}
                  />
                  {uploadError && (
                    <div className="modal-error-text">
                      {uploadError}
                    </div>
                  )}
                  {customTickers.length > 0 && (
                    <div className="modal-muted-text">
                      <strong>{uploadFileName}</strong> - {t("optimizer.tickersLoaded", "Loaded tickers: {{count}}", { count: customTickers.length })}
                      <ul className="optimizer-weights-list optimizer-compact-list">
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
            <div className="optimizer-progress-container">
              <div className="optimizer-progress-bar-bg">
                <div
                  className="optimizer-progress-bar-fill"
                  style={{ "--optimizer-progress": `${progress.percentage}%` }}
                />
              </div>
              <p className="optimizer-progress-copy">
                {progress.percentage}% - {progress.message}
              </p>
              <p className="optimizer-progress-note">
                {t("optimizer.backgroundJobNote", "You can leave this screen; the optimizer will reconnect while this app remains open.")}
              </p>
              <button
                type="button"
                className="optimizer-secondary-button optimizer-cancel-button"
                onClick={handleCancelOptimization}
                disabled={cancelRequested}
              >
                {cancelRequested
                  ? t("optimizer.cancelling", "Cancelling...")
                  : t("optimizer.cancel", "Cancel")}
              </button>
            </div>
          )}
        </form>
      </section>

      {error && (
        <div className="optimizer-error optimizer-error-strong">
          <div className="optimizer-error-title">{t("common.error", "Error")}</div>
          <div>{error}</div>
          {errorDetails && (
            <div className="optimizer-error-details">
              {errorDetails}
            </div>
          )}
        </div>
      )}

      {loading && <OptimizerSkeleton />}

      {!loading && !optimizedPortfolio && !error && (
        <section className="optimizer-awaiting-results" aria-labelledby="optimizer-awaiting-title">
          <span className="optimizer-awaiting-index">{t("optimizer.nextLabel", "Next")}</span>
          <div>
            <h2 id="optimizer-awaiting-title">{t("optimizer.awaitingTitle", "Allocation results will appear here")}</h2>
            <p>{t("optimizer.awaitingHelp", "Complete the brief and run the optimizer to review expected return, risk, Sharpe ratio, and target weights.")}</p>
          </div>
          <div className="optimizer-awaiting-fields" aria-hidden="true">
            <span>{t("optimizer.return", "Expected Return")}</span>
            <span>{t("optimizer.risk", "Risk")}</span>
            <span>{t("optimizer.weights", "Weights")}</span>
          </div>
        </section>
      )}

      {!loading && optimizedPortfolio && (
        <>
          <section className="optimizer-results-container" aria-labelledby="optimizer-results-title">
            <div className="optimizer-results-header">
              <div>
                <span className="optimizer-section-eyebrow">{t("optimizer.resultKicker", "Model output")}</span>
                <h2 id="optimizer-results-title">{t("optimizer.results")}</h2>
                <p>{t("optimizer.resultHelp", "Review the modeled tradeoff first, then inspect the target weights.")}</p>
              </div>
              <button
                className="optimizer-secondary-button"
                onClick={handleDownloadPortfolio}
                disabled={!optimizedPortfolio}
                type="button"
              >
                {t("optimizer.downloadPortfolio", "Download JSON")}
              </button>
            </div>

            <div className="optimizer-result-summary">
              <div className="optimizer-result-primary">
                <span>{t("optimizer.return")}</span>
                <strong>{(optimizedPortfolio.return * 100).toFixed(2)}%</strong>
                <p>{t("optimizer.returnContext", "Modeled expected return for the optimized mix.")}</p>
              </div>
              <dl className="optimizer-result-secondary">
                <div>
                  <dt>{t("optimizer.risk")}</dt>
                  <dd>{(optimizedPortfolio.risk * 100).toFixed(2)}%</dd>
                  <small>{t("optimizer.riskContext", "Modeled standard deviation")}</small>
                </div>
                <div>
                  <dt>{t("optimizer.sharpeRatio")}</dt>
                  <dd>{optimizedPortfolio.sharpe_ratio.toFixed(2)}</dd>
                  <small>{t("optimizer.sharpeContext", "Return per unit of modeled risk")}</small>
                </div>
              </dl>
            </div>

            <div className="optimizer-weights-card">
              <div className="optimizer-weights-header">
                <div>
                  <span className="optimizer-section-eyebrow">{t("optimizer.composition", "Composition")}</span>
                  <h3>{t("optimizer.weights")}</h3>
                </div>
                <div className="manager-display-toggle no-print">
                  <span className="display-toggle-label">
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
                      aria-pressed={securityDisplayMode === mode.key}
                      className={`manager-display-toggle-button is-compact ${securityDisplayMode === mode.key ? "optimizer-submit-button" : "optimizer-secondary-button"}`}
                    >
                      {mode.label}
                    </button>
                  ))}
                </div>
              </div>
              <ul className="optimizer-weights-list">
                {Object.entries(optimizedPortfolio.weights).map(([ticker, weight]) => (
                  <li key={ticker} style={{ "--portfolio-weight": `${Math.max(weight * 100, 0.5)}%` }}>
                    <span className="optimizer-weight-name">{formatPortfolioTicker(ticker)}</span>
                    <strong>{(weight * 100).toFixed(2)}%</strong>
                    <span className="optimizer-weight-mark" aria-hidden="true" />
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="investment-allocation-container" aria-labelledby="optimizer-allocation-title">
            <div className="investment-allocation-header">
              <div>
                <span className="optimizer-section-eyebrow">{t("optimizer.executionPlan", "Execution plan")}</span>
                <h2 id="optimizer-allocation-title">{t("optimizer.investmentAllocation")}</h2>
                <p>{t("optimizer.allocationHelp", "Convert target weights into a budget-aware share plan.")}</p>
              </div>
            </div>
            <div className="investment-allocation-form">
              <div className="optimizer-form-group">
                <label htmlFor="investmentBudget">{t("optimizer.investmentBudget")}</label>
                <input
                  id="investmentBudget"
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
              <button type="button" onClick={handleAllocation} className="optimizer-submit-button">
                {t("optimizer.calculate")}
              </button>
            </div>
            
            {allocation && (
              <div className="allocation-results-container">
                <h3>{t("optimizer.allocationResults")}</h3>
                <div className="allocation-table-shell">
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
                                  aria-label={t("optimizer.fractionalForTicker", "Allow fractional shares for {{ticker}}", { ticker })}
                                />
                                <span className="toggle-slider" />
                              </label>
                            </td>
                          </tr>
                        ))}
                      {allocation.remainingCash > 0.01 && (
                        <tr className="allocation-muted-row">
                          <td>{t("optimizer.remainingCash", "Remaining Cash")}</td>
                          <td>{t("optimizer.notApplicable", "N/A")}</td>
                          <td>{t("optimizer.notApplicable", "N/A")}</td>
                          <td>${allocation.remainingCash.toFixed(2)}</td>
                          <td />
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <small className="optimizer-field-note">
                  {t("optimizer.hybridNote", "Toggle fractional per ticker. Integer-only tickers are floored; freed capital is redistributed to fractional-eligible tickers.")}
                </small>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default Optimizer
