"use client"

import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

const FutureDateInput = ({ onFutureDaysChange, initialDays = 30 }) => {
  const [days, setDays] = useState(initialDays)
  const { t } = useTranslation()
  const updateTimeoutRef = useRef(null)

  useEffect(() => () => clearTimeout(updateTimeoutRef.current), [])

  const scheduleFutureDaysChange = (newDays) => {
    clearTimeout(updateTimeoutRef.current)
    updateTimeoutRef.current = setTimeout(() => {
      if (newDays && onFutureDaysChange) {
        onFutureDaysChange(Number.parseInt(newDays, 10))
      }
    }, 500)
  }

  const handleChange = (e) => {
    const newDays = e.target.value
    setDays(newDays)

    if (newDays && Number.parseInt(newDays, 10) > 0) {
      scheduleFutureDaysChange(newDays)
    }
  }

  return (
    <div className="date-input-container">
      <div className="date-input-group">
        <label htmlFor="future-days">{t("future.days_to_predict", "Days to Predict")}</label>
        <input
          type="number"
          id="future-days"
          value={days}
          onChange={handleChange}
          min="1"
          max="365"
          title="Predictions will auto-update when you change this value"
        />
      </div>
    </div>
  )
}

export default FutureDateInput
