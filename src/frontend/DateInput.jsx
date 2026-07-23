"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

const DATE_PRESETS = [
  { key: "1m", months: 1, translationKey: "date.oneMonth", fallbackLabel: "1M" },
  { key: "3m", months: 3, translationKey: "date.threeMonths", fallbackLabel: "3M" },
  { key: "6m", months: 6, translationKey: "date.sixMonths", fallbackLabel: "6M" },
  { key: "ytd", translationKey: "date.ytd", fallbackLabel: "YTD" },
  { key: "1y", years: 1, translationKey: "date.oneYear", fallbackLabel: "1Y" },
  { key: "5y", years: 5, translationKey: "date.fiveYears", fallbackLabel: "5Y" },
]

const formatLocalDate = (date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

const shiftCalendarDate = (date, { months = 0, years = 0 }) => {
  const targetYear = date.getFullYear() - years
  const targetMonth = date.getMonth() - months
  const lastDayOfTargetMonth = new Date(targetYear, targetMonth + 1, 0).getDate()

  return new Date(targetYear, targetMonth, Math.min(date.getDate(), lastDayOfTargetMonth))
}

const getPresetRange = (preset) => {
  const endDate = new Date()
  endDate.setHours(0, 0, 0, 0)
  endDate.setDate(endDate.getDate() - 1)

  let startDate
  if (preset.key === "ytd") {
    startDate = new Date(endDate.getFullYear(), 0, 1)
    if (startDate >= endDate) {
      startDate = new Date(endDate.getFullYear() - 1, 0, 1)
    }
  } else {
    startDate = shiftCalendarDate(endDate, preset)
  }

  return {
    startDate: formatLocalDate(startDate),
    endDate: formatLocalDate(endDate),
  }
}

function DateInput({ onDateRangeChange, notifyInitial = true, inputIdPrefix = "date" }) {
  const { t } = useTranslation()
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [activePreset, setActivePreset] = useState("3m")
  const updateTimeoutRef = useRef(null)
  const immediateRangeRef = useRef(null)
  const isInitialSetupRef = useRef(true)

  useEffect(() => {
    const initialRange = getPresetRange(DATE_PRESETS.find((preset) => preset.key === "3m"))
    setEndDate(initialRange.endDate)
    setStartDate(initialRange.startDate)
  }, [])

  useEffect(() => {
    if (!startDate || !endDate || !onDateRangeChange) return undefined

    const currentRange = `${startDate}:${endDate}`
    if (immediateRangeRef.current === currentRange) {
      immediateRangeRef.current = null
      return undefined
    }

    if (isInitialSetupRef.current) {
      isInitialSetupRef.current = false
      if (!notifyInitial) return undefined
    }

    clearTimeout(updateTimeoutRef.current)
    updateTimeoutRef.current = setTimeout(() => {
      onDateRangeChange(startDate, endDate)
    }, 500)

    return () => clearTimeout(updateTimeoutRef.current)
  }, [startDate, endDate, notifyInitial, onDateRangeChange])

  const startDateId = `${inputIdPrefix}-start`
  const endDateId = `${inputIdPrefix}-end`
  const presetLabelId = `${inputIdPrefix}-presets-label`

  const handlePresetChange = (preset) => {
    const range = getPresetRange(preset)
    clearTimeout(updateTimeoutRef.current)
    immediateRangeRef.current = `${range.startDate}:${range.endDate}`
    setActivePreset(preset.key)
    setStartDate(range.startDate)
    setEndDate(range.endDate)
    onDateRangeChange?.(range.startDate, range.endDate)
  }

  return (
    <div className="date-input-container stock-date-input-container">
      <div className="date-input-group stock-date-start">
        <label htmlFor={startDateId}>{t("date.start")}</label>
        <input
          type="date"
          id={startDateId}
          value={startDate}
          max={endDate || undefined}
          onChange={(e) => {
            immediateRangeRef.current = null
            setActivePreset(null)
            setStartDate(e.target.value)
          }}
          title={t("date.autoUpdateTitle", "Chart will auto-update when both dates are selected")}
        />
      </div>
      <div className="date-input-group stock-date-end">
        <label htmlFor={endDateId}>{t("date.end")}</label>
        <input
          type="date"
          id={endDateId}
          value={endDate}
          min={startDate || undefined}
          onChange={(e) => {
            immediateRangeRef.current = null
            setActivePreset(null)
            setEndDate(e.target.value)
          }}
          title={t("date.autoUpdateTitle", "Chart will auto-update when both dates are selected")}
        />
      </div>
      <div className="date-preset-panel">
        <span className="date-preset-label" id={presetLabelId}>
          {t("date.quickRange", "Quick range")}
        </span>
        <div className="date-preset-group" role="group" aria-labelledby={presetLabelId}>
          {DATE_PRESETS.map((preset) => (
            <button
              className="date-preset-button"
              type="button"
              key={preset.key}
              aria-pressed={activePreset === preset.key}
              onClick={() => handlePresetChange(preset)}
            >
              {t(preset.translationKey, preset.fallbackLabel)}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default DateInput
