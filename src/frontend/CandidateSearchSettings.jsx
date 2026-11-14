import { useState } from "react"
import { useTranslation } from "react-i18next"
import { apiUrl } from "./apiClient.js"

import { DEFAULT_CANDIDATE_SEARCH } from "./candidateSearchDefaults.js"

export function CandidateSearchSummary({ value }) {
  const { t } = useTranslation()
  const text = key => t(`candidateSearch.${key}`)
  if (!value) return <p className="strategy-note">{text("legacy")}</p>
  return <details className="candidate-summary"><summary>{text("details")}</summary>
    <p>{text("mode")}: {text(value.mode_effective)} · {text("mapDate")}: {value.map_as_of || "—"} · {text("forecastDate")}: {value.as_of || "—"}</p>
    <p>{text("selected")}: {value.selected_count} / {value.universe_count} · {text("calls")}: {value.prediction_calls ?? "—"} · {text("cacheHits")}: {value.cache_hits ?? "—"} · {text("failures")}: {value.failures || 0}</p>
    <p>{text("held")}: {value.held?.length || 0} · {text("similar")}: {value.similar?.length || 0} · {text("random")}: {value.random?.length || 0}</p>
    <p>{text("cycle")}: {value.cycle ?? "—"} · {text("remaining")}: {value.remaining_in_cycle ?? "—"} · {text("mapAge")}: {value.map_age_sessions ?? "—"}</p>
    {value.initial && <p>{text("initial")}</p>}
    {value.limited_savings && <p className="strategy-note">{text("limitedSavings")}</p>}
    <p className="strategy-note">{text("referenceNote")}</p>
    {Object.entries(value.failures_by_ticker || {}).map(([ticker, failure]) => <p key={ticker}>{ticker}: {failure.reason || failure.no_view_reason || failure.source || "no_view"}</p>)}
    <div className="candidate-symbols">{["held", "similar", "random", "required"].map(key => value[key]?.length > 0 &&
      <p key={key}><strong>{text(key)}:</strong> {value[key].join(", ")}</p>)}</div>
  </details>
}

export default function CandidateSearchSettings({ value = DEFAULT_CANDIDATE_SEARCH, onChange,
  riskOnly = false, campaignId, onReset, previewInput, idPrefix = "candidate" }) {
  const { t } = useTranslation()
  const text = key => t(`candidateSearch.${key}`)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState("")
  const update = (key, next) => { onChange({ ...value, [key]: next }); setPreview(null) }
  const inspect = async () => {
    setError("")
    try {
      const response = await fetch(apiUrl("/api/candidate-search/preview"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...previewInput, candidate_search: value, campaign_id: campaignId,
          forecast_method: riskOnly ? "RISK_ONLY" : previewInput?.forecast_method }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)
      setPreview(data)
    } catch (err) { setError(err.message) }
  }
  return <details className="candidate-settings"><summary>{text("title")}</summary>
    <label className="candidate-enabled"><input type="checkbox" checked={value.enabled}
      onChange={e => update("enabled", e.target.checked)} />{text("enabled")}</label>
    {value.enabled && <>
      <p className="strategy-note">{text("holdingNote")}</p>
      <label htmlFor={`${idPrefix}-mode`}>{text("mode")}</label>
      <select id={`${idPrefix}-mode`} value={riskOnly ? "price_features" : value.mode} disabled={riskOnly}
        onChange={e => update("mode", e.target.value)}>
        {["forecast_profile", "price_features", "frozen_forecast"].map(mode => <option key={mode} value={mode}>{text(mode)}</option>)}
      </select>
      {riskOnly && <p>{text("riskOnly")}</p>}
      <div className="candidate-fields">{["similar_count", "explore_count", "seed", "refresh_interval"].map(key =>
        <label key={key} htmlFor={`${idPrefix}-${key}`}>{text(key)}<input id={`${idPrefix}-${key}`} type="number"
          min={key === "refresh_interval" ? 1 : 0} max={key === "seed" ? 4294967295 : key === "refresh_interval" ? 2520 : 2000}
          step="1" value={value[key]} disabled={key === "refresh_interval" && (riskOnly || value.mode !== "forecast_profile")}
          onChange={e => update(key, e.target.value === "" ? "" : Number(e.target.value))} /></label>)}</div>
      <p className="strategy-note">{text("referenceNote")}</p>
      {campaignId && <div><small>{text("context")}: {campaignId}</small>
        {onReset && <button type="button" onClick={() => { onReset(); setPreview(null) }}>{text("reset")}</button>}</div>}
    </>}
    {previewInput && <button type="button" onClick={inspect}>{text("preview")}</button>}
    {error && <p role="alert">{error}</p>}
    {preview && <div role="status"><p>{text("selected")}: {preview.estimated_selected_count} / {preview.universe_count}</p>
      <p>{text("mapDate")}: {preview.map_as_of || "—"} · {text("mapAge")}: {preview.map_age_sessions ?? "—"} · {text("cycleEstimate")}: {preview.estimated_cycle_steps ?? "—"}</p>
      <p className="strategy-note">{text("previewEstimate")}</p>
      {preview.full_refresh_expected && <p>{text("fullExpected")}</p>}
      {preview.reset_required && <p>{text("contextChanged")}</p>}
      {preview.initial && <p>{text("initial")}</p>}{preview.limited_savings && <p>{text("limitedSavings")}</p>}
    </div>}
  </details>
}
