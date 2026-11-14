import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import DateInput from "./DateInput.jsx"
import Plot from "./LazyPlot.jsx"
import CandidateSearchSettings, { CandidateSearchSummary } from "./CandidateSearchSettings.jsx"
import { DEFAULT_CANDIDATE_SEARCH } from "./candidateSearchDefaults.js"
import { apiUrl } from "./apiClient.js"

const JOB_KEY = "antifier.strategyBacktest.job"
const FORECASTS = [["LIGHTWEIGHT", "lightweight"], ["ARIMA_TRANSFORMER", "ensemble"], ["TRANSFORMER", "transformer"]]
const OPTIMIZERS = [["MIN_VARIANCE", "minVariance"], ["MPT", "mpt"], ["BL", "bl"], ["GMV_MODEL", null]]
const DEFAULTS = { train_window: 504, rebalance_frequency: 63, forecast_horizon: 63,
  initial_value: 10000, max_asset_weight: 20, transaction_cost_bps: 10,
  rebalance_band: 2, max_turnover: 35, risk_free_rate: 2 }

async function request(path, options) {
  const response = await fetch(apiUrl(path), options)
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.error || `HTTP ${response.status}`)
    error.status = response.status
    throw error
  }
  return data
}

export default function StrategyBacktest() {
  const { t } = useTranslation()
  const label = (key, options) => t(`strategyBacktest.${key}`, options)
  const [csv, setCsv] = useState("")
  const [filename, setFilename] = useState("")
  const [universe, setUniverse] = useState(null)
  const [readingCsv, setReadingCsv] = useState(false)
  const csvInput = useRef(null)
  const [fields, setFields] = useState(DEFAULTS)
  const [dates, setDates] = useState({})
  const [strategies, setStrategies] = useState([
    { rowId: 0, optimization_method: "MIN_VARIANCE", forecast_method: "RISK_ONLY", candidate_search: { ...DEFAULT_CANDIDATE_SEARCH } },
  ])
  const nextRowId = useRef(1)
  const [preview, setPreview] = useState(null)
  const [jobId, setJobId] = useState(() => localStorage.getItem(JOB_KEY) || "")
  const [job, setJob] = useState(null)
  const [pollGeneration, setPollGeneration] = useState(0)
  const [result, setResult] = useState(null)
  const [saved, setSaved] = useState([])
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [selectedDate, setSelectedDate] = useState("")
  const fileVersion = useRef(0)
  const running = Boolean(jobId && (!job || job.status === "running"))
  const refreshSaved = () => request("/api/strategy-backtest-results").then(data => setSaved(data.ids))
  useEffect(() => { refreshSaved().catch(() => {}) }, [])
  useEffect(() => {
    if (!jobId) return
    let disposed = false
    let timer
    const poll = async () => {
      try {
        const data = await request(`/api/optimization-jobs/${jobId}`)
        if (disposed) return
        setJob(data)
        if (data.status === "running") { setError(""); timer = setTimeout(poll, 2000) }
        else {
          localStorage.removeItem(JOB_KEY)
          if (data.status === "completed") {
            setError(""); setResult(data.result)
            refreshSaved().catch(() => {})
          } else setError(data.error || data.message)
        }
      } catch (err) {
        if (!disposed) {
          setError(err.message)
          if (err.status === 404) {
            localStorage.removeItem(JOB_KEY)
            setJob({ status: "failed" })
          } else timer = setTimeout(poll, 5000)
        }
      }
    }
    poll()
    return () => { disposed = true; clearTimeout(timer) }
  }, [jobId, pollGeneration])

  const changeDates = useCallback((start_date, end_date) => {
    setDates({ start_date, end_date }); setPreview(null)
  }, [])
  const change = (key, value) => { setFields(old => ({ ...old, [key]: value })); setPreview(null) }
  const payload = () => ({ csv, ...dates, ...fields,
    strategy_configs: strategies.map(({ optimization_method, forecast_method, candidate_search, campaign_id }) => ({ optimization_method, forecast_method, candidate_search, campaign_id })),
    max_asset_weight: Number(fields.max_asset_weight) / 100,
    rebalance_band: Number(fields.rebalance_band) / 100,
    max_turnover: Number(fields.max_turnover) / 100,
    risk_free_rate: Number(fields.risk_free_rate) / 100 })
  const post = body => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  const inspect = async event => {
    event.preventDefault(); setBusy(true); setError("")
    try { setPreview(await request("/api/strategy-backtests/preview", post(payload()))) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const start = async () => {
    setBusy(true); setError("")
    try {
      const data = await request("/api/strategy-backtests", post(payload()))
      localStorage.setItem(JOB_KEY, data.request_id)
      setJob(null); setResult(null); setSelectedDate(""); setJobId(data.request_id)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const upload = async event => {
    const file = event.target.files?.[0]
    const version = ++fileVersion.current
    setPreview(null); setCsv(""); setFilename(""); setUniverse(null); setError("")
    event.target.value = ""
    if (!file) return
    if (file.size > 1000000) { setError(label("fileTooLarge")); return }
    setReadingCsv(true)
    try {
      let text
      if (file.arrayBuffer) {
        const bytes = new Uint8Array(await file.arrayBuffer())
        const encoding = bytes[0] === 0xff && bytes[1] === 0xfe ? "utf-16le"
          : bytes[0] === 0xfe && bytes[1] === 0xff ? "utf-16be" : "utf-8"
        try { text = new TextDecoder(encoding, { fatal: true }).decode(bytes) }
        catch { text = new TextDecoder("euc-kr", { fatal: true }).decode(bytes) }
      } else text = await file.text()
      if (version !== fileVersion.current) return
      const data = await request("/api/strategy-backtests/universe", post({ csv: text }))
      if (version !== fileVersion.current) return
      setCsv(text); setFilename(file.name); setUniverse(data)
    } catch (err) {
      if (version === fileVersion.current) setError(err.status === 404 ? label("restartBackend") : err.message || label("readError"))
    } finally {
      if (version === fileVersion.current) setReadingCsv(false)
    }
  }

  const load = async id => {
    if (!id) return
    setError("")
    try {
      const data = await request(`/api/portfolio-results/${id}`)
      if (data.result_type !== "strategy_backtest") throw new Error(label("invalidResult"))
      setResult(data); setSelectedDate("")
    } catch (err) { setError(err.message) }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }))
    const anchor = document.createElement("a")
    anchor.href = url; anchor.download = "strategy-backtest.json"; anchor.click(); URL.revokeObjectURL(url)
  }
  const changeStrategy = (rowId, key, value) => {
    setStrategies(old => old.map(row => {
      if (row.rowId !== rowId) return row
      const next = { ...row, [key]: value }
      if (next.optimization_method === "MIN_VARIANCE") next.forecast_method = "RISK_ONLY"
      else if (next.forecast_method === "RISK_ONLY") next.forecast_method = "LIGHTWEIGHT"
      return next
    }))
    setPreview(null)
  }
  const addStrategy = () => {
    const candidates = OPTIMIZERS.flatMap(([optimization_method]) =>
      (optimization_method === "MIN_VARIANCE" ? ["RISK_ONLY"] : FORECASTS.map(([method]) => method))
        .map(forecast_method => ({ optimization_method, forecast_method })))
    const next = candidates.find(c => !strategies.some(row =>
      row.optimization_method === c.optimization_method && row.forecast_method === c.forecast_method))
    if (next) {
      const row = { ...next, rowId: nextRowId.current++, candidate_search: { ...DEFAULT_CANDIDATE_SEARCH } }
      setStrategies(old => [...old, row])
    }
    setPreview(null)
  }
  const strategyLabel = name => {
    const config = result?.settings?.strategy_configs?.find(c => c.id === name)
    if (!config) return label(name)
    const optimizer = config.optimization_method === "GMV_MODEL" ? label("gmv_model")
      : t(`optimizer.${OPTIMIZERS.find(([value]) => value === config.optimization_method)[1]}`)
    if (config.optimization_method === "MIN_VARIANCE") return optimizer + (config.candidate_search ? ` · ${t(`candidateSearch.${config.candidate_search.enabled ? "price_features" : "full"}`)}` : "")
    return `${optimizer} · ${t(`optimizer.${FORECASTS.find(([value]) => value === config.forecast_method)[1]}`)}` +
      (config.candidate_search ? ` · ${t(`candidateSearch.${config.candidate_search.enabled ? (config.optimization_method === "MIN_VARIANCE" ? "price_features" : config.candidate_search.mode) : "full"}`)}` : "")
  }
  const names = result ? Object.keys(result.strategies) : []
  const plot = (key, percent = false) => <Plot data={names.map(name => ({
    x: Object.keys(result.strategies[name][key]), y: Object.values(result.strategies[name][key]),
    type: "scatter", mode: "lines", name: strategyLabel(name),
  }))} layout={{ autosize: true, height: 340, margin: { t: 25, l: 60, r: 20, b: 50 },
    paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#aeb49f" },
    hovermode: "x unified", yaxis: { tickformat: percent ? ".1%" : ",.0f" },
    legend: { orientation: "h" } }} config={{ responsive: true, displaylogo: false }} style={{ width: "100%" }} />
  const metrics = ["cagr", "annual_volatility", "sharpe", "max_drawdown", "avg_controlled_turnover", "transaction_costs"]
  const format = (key, value) => value == null ? "—" : key === "sharpe" ? Number(value).toFixed(3)
    : key === "transaction_costs" ? Number(value).toFixed(2) : `${(value * 100).toFixed(2)}%`
  const records = names.length ? result.strategies[names[0]].rebalance_records : []
  return <section className="strategy-backtest" aria-labelledby="strategy-backtest-title">
    <h2 id="strategy-backtest-title">{label("title")}</h2>
    <p>{label("description")}</p>
    <details className="strategy-limitations"><summary>{label("conditions")}</summary><p className="strategy-note">{label("limitations")}</p></details>
    <form onSubmit={inspect}>
      <fieldset disabled={running || busy || readingCsv}>
        <legend>{label("setup")}</legend>
        <div className="strategy-source">
          <label htmlFor="strategy-csv-file">{label("csv")}</label>
          <input ref={csvInput} id="strategy-csv-file" className="hidden-file-input" type="file"
            accept=".csv,text/csv,text/plain" onChange={upload} />
          <div className="strategy-file-row">
            <button type="button" onClick={() => csvInput.current?.click()}>{readingCsv ? label("readingCsv") : label("chooseCsv")}</button>
            <span className="strategy-file-name" title={filename}>{filename || label("noFile")}</span>
          </div>
          <small>{label("csvHint")}</small>
          {universe && <div className="strategy-universe" role="status">
            <strong>{t("strategyBacktest.recognized", { count: universe.tickers.length })}</strong>
            <p>{universe.tickers.slice(0, 12).join(", ")}{universe.tickers.length > 12 ? " …" : ""}</p>
            {universe.duplicates.length > 0 && <small>{label("duplicates")}: {universe.duplicates.join(", ")}</small>}
          </div>}
        </div>
        <DateInput inputIdPrefix="strategy-dates" onDateRangeChange={changeDates} />
        <div className="strategy-fields">{Object.entries(fields).map(([key, value]) => <label key={key}>
          {label(key)}<input type="number" required step={key === "initial_value" || key.includes("window") || key.includes("frequency") || key.includes("horizon") ? "1" : "0.01"}
            value={value} onChange={e => change(key, e.target.value)} />
        </label>)}</div>
        <h3>{label("comparisonItems")}</h3>
        {strategies.map((row, index) => <div className="strategy-config-row" key={row.rowId}>
          <label htmlFor={`strategy-optimizer-${row.rowId}`}>{t("optimizer.optimizationMethod")}
            <select id={`strategy-optimizer-${row.rowId}`} value={row.optimization_method}
              onChange={e => changeStrategy(row.rowId, "optimization_method", e.target.value)}>
              {OPTIMIZERS.map(([method, key]) => <option key={method} value={method}>
                {key ? t(`optimizer.${key}`) : label("gmv_model")}
              </option>)}
            </select>
          </label>
          <label htmlFor={`strategy-forecast-${row.rowId}`}>{t("optimizer.forecastMethod")}
            <select id={`strategy-forecast-${row.rowId}`} value={row.forecast_method}
              disabled={row.optimization_method === "MIN_VARIANCE"}
              onChange={e => changeStrategy(row.rowId, "forecast_method", e.target.value)}>
              {row.optimization_method === "MIN_VARIANCE" ? <option value="RISK_ONLY">{t("optimizer.riskOnlyForecast")}</option>
                : FORECASTS.map(([method, key]) => <option key={method} value={method}>{t(`optimizer.${key}`)}</option>)}
            </select>
          </label>
          <button type="button" disabled={strategies.length === 1}
            aria-label={`${label("removeStrategy")} ${index+1}`} onClick={() => {
              setStrategies(old => old.filter(item => item.rowId !== row.rowId)); setPreview(null)
            }}>{label("removeStrategy")}</button>
          <CandidateSearchSettings value={row.candidate_search} onChange={next => changeStrategy(row.rowId, "candidate_search", next)}
            riskOnly={row.optimization_method === "MIN_VARIANCE"} idPrefix={`search-${row.rowId}`} />
        </div>)}
        <button type="button" disabled={strategies.length >= 10} onClick={addStrategy}>{label("addStrategy")}</button>
        {strategies.some(row => row.optimization_method === "BL") && <p className="strategy-note">{label("blPriorNote")}</p>}
        <button type="submit" disabled={!csv || !universe || !dates.start_date || !strategies.length || readingCsv}>{label("preview")}</button>
        {preview && <div role="status">
          <p>{label("workload")}: {preview.tickers.length} / {preview.estimated_rebalances}</p>
          <p>{label("forecastUpperBound")}: {preview.estimated_forecasts}</p>
          {preview.initial_forecasts_upper_bound != null && <p>{label("sharedInitialForecasts")}: {preview.initial_forecasts_upper_bound}</p>}
          {preview.forecast_workloads?.map(row => <div key={row.id} className="candidate-summary">
            <strong>{row.optimization_method} / {row.forecast_method} / {t(`candidateSearch.${row.mode}`)}</strong>
            {row.forecast_method === "RISK_ONLY" ? <p>{label("noModelForecasts")}</p> : <>
              <p>{label("initialForecasts")}: {row.initial_forecasts_upper_bound}</p>
              <p>{label("fullForecastSteps")}: {row.full_rebalances} · {label("partialForecastSteps")}: {row.partial_rebalances}</p>
              {row.mode === "full" ? <p>{label("fullForecastTotal")}: {row.total_before_cache}</p> : <>
                <p>{label("partialForecastFormula", { universe: preview.tickers.length, similar: row.similar_count, explore: row.explore_count })}</p>
                <p>{label("forecastTotalUnknown")}</p>
                <p>{label(row.mode === "frozen_forecast" ? "frozenWorkload" : row.mode === "price_features" ? "priceWorkload" : "periodicWorkload", { interval: row.refresh_interval })}</p>
              </>}
            </>}
            {row.mode !== "full" && row.explore_count > 0 && <p>{t("candidateSearch.cycleEstimate")}: {Math.ceil(preview.tickers.length / row.explore_count)}</p>}
          </div>)}
          <p className="strategy-note">{label("workloadEstimateNote")}</p>
          <p className="strategy-note">{label("sharedForecastNote")}</p>
          <p>{label("duplicates")}: {preview.duplicates.join(", ") || "—"}</p>
          <button type="button" onClick={start}>{label("run")}</button>
        </div>}
      </fieldset>
    </form>
    {job && ["interrupted", "failed", "error", "cancelled"].includes(job.status) && <button type="button" onClick={async () => {
      try {
        const value = await request(`/api/strategy-backtests/${jobId}/resume`, post({}))
        localStorage.setItem(JOB_KEY, jobId); setJob(value); setError(""); setPollGeneration(old => old+1)
      } catch (err) { setError(err.message) }
    }}>{t("candidateSearch.resume", "Resume saved backtest")}</button>}
    {error && <p role="alert">{error}</p>}
    {running && <div role="status"><progress value={job?.progress || 0} max="100" />
      <p>{job?.message || label("queued")}</p>
      <button type="button" onClick={async () => {
        try { await request(`/api/optimization-jobs/${jobId}/cancel`, post({})) }
        catch (err) { setError(err.message) }
      }}>{label("cancel")}</button>
    </div>}
    {saved.length > 0 && <label>{label("saved")}<select defaultValue="" disabled={running} onChange={e => load(e.target.value)}>
      <option value="">—</option>{saved.map(id => <option key={id} value={id}>{id}</option>)}
    </select></label>}
    {result && <section className="strategy-results">
      <h3>{label("results")}</h3><button type="button" onClick={download}>{label("download")}</button>
      <p>{label("effectiveDates")}: {result.effective_start_date} ~ {result.effective_end_date}</p>
      <p>{label("eligible")}: {result.eligible_tickers.join(", ")}</p>
      <p>{label("excluded")}: {Object.keys(result.exclusions).join(", ") || "—"}</p>
      <details><summary>{label("conditions")}</summary><dl>{Object.keys(DEFAULTS).map(key =>
        <div key={key}><dt>{label(key)}</dt><dd>{["max_asset_weight", "rebalance_band", "max_turnover", "risk_free_rate"].includes(key)
          ? (result.settings[key] * 100).toFixed(2) : result.settings[key]}</dd></div>)}</dl></details>
      <h3>{label("equity")}</h3>{plot("equity")}
      <h3>{label("drawdown")}</h3>{plot("drawdown", true)}
      <div className="strategy-table"><table><thead><tr><th>{label("strategy")}</th>
        {metrics.map(key => <th key={key}>{label(key)}</th>)}</tr></thead><tbody>{names.map(name => <tr key={name}>
          <th scope="row">{strategyLabel(name)}</th>{metrics.map(key => <td key={key}>{format(key, result.strategies[name].summary[key])}</td>)}
        </tr>)}</tbody></table></div>
      <p className="strategy-note">{label("turnoverHint")}</p>
      <label>{label("rebalanceDetail")}<select value={selectedDate} onChange={e => setSelectedDate(e.target.value)}>
        <option value="">—</option>{records.map(r => <option key={r.rebalance_date}>{r.rebalance_date}</option>)}
      </select></label>
      {selectedDate && <div>
        <p>{label("trainEnd")}: {result.forecast_records.find(r => r.date === selectedDate)?.train_end_date}</p>
        {names.map(name => {
          const record = result.strategies[name].rebalance_records.find(r => r.rebalance_date === selectedDate)
          const forecast = result.forecast_records.find(r => r.date === selectedDate)
          const config = result.settings.strategy_configs?.find(c => c.id === name)
          const predictions = forecast.forecasts_by_strategy?.[name] || forecast.forecasts_by_method?.[config?.forecast_method] ||
            (config?.forecast_method === "RISK_ONLY" ? { annual_log_forecasts: {}, no_view_tickers: [] } : forecast)
          const diagnostic = forecast.strategy_diagnostics?.[name]
          const fallback = diagnostic?.fallback_reason ?? (name === "model_mpt" ? forecast.mpt_fallback : null)
          return <div key={name}><h4>{strategyLabel(name)}</h4>
            <CandidateSearchSummary value={forecast.candidate_search?.[name]} />
            <p>{label("fallback")}: {fallback || "—"}</p>
            <p>{label("noView")}: {predictions.no_view_tickers.join(", ") || "—"}</p>
            {diagnostic?.prior_source && <p className="strategy-note">{label("blPriorNote")}</p>}
            <div className="strategy-table"><table><thead><tr><th>{label("ticker")}</th><th>{label("forecast")}</th></tr></thead>
              <tbody>{Object.entries(predictions.annual_log_forecasts).map(([ticker, value]) =>
                <tr key={ticker}><td>{ticker}</td><td>{format("forecast", value)}</td></tr>)}</tbody></table></div>
            <p>{label("periodReturn")}: {format("return", record.net_period_return)} ({record.rebalance_date} ~ {record.period_end_date})</p>
            <div className="strategy-table"><table><thead><tr><th>{label("ticker")}</th><th>{label("weight")}</th></tr></thead>
              <tbody>{Object.entries(record.controlled_weights).filter(([, w]) => w > 0).map(([ticker, w]) =>
                <tr key={ticker}><td>{ticker}</td><td>{format("weight", w)}</td></tr>)}</tbody></table></div>
          </div>
        })}
      </div>}
    </section>}
  </section>
}
