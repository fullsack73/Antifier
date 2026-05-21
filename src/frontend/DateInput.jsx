"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

function DateInput({ onDateRangeChange, notifyInitial = true, inputIdPrefix = "date" }) {
  const { t } = useTranslation()
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const updateTimeoutRef = useRef(null)
  const isInitialSetupRef = useRef(true)

  useEffect(() => {
    // set default dates (3 months from yesterday)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    const threeMonthsAgo = new Date(yesterday)
    threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3)

    // format dates for input fields (YYYY-MM-DD)
    const formatDate = (date) => {
      return date.toISOString().split("T")[0]
    }

    setEndDate(formatDate(yesterday))
    setStartDate(formatDate(threeMonthsAgo))
  }, [])

  useEffect(() => {
    if (!startDate || !endDate || !onDateRangeChange) return undefined

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

  return (
    <div className="date-input-container">
      <div className="date-input-group">
        <label htmlFor={startDateId}>{t("date.start")}</label>
        <input
          type="date"
          id={startDateId}
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          title="Chart will auto-update when both dates are selected"
        />
      </div>
      <div className="date-input-group">
        <label htmlFor={endDateId}>{t("date.end")}</label>
        <input
          type="date"
          id={endDateId}
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          title="Chart will auto-update when both dates are selected"
        />
      </div>
    </div>
  )
}

export default DateInput
