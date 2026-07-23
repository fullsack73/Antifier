import { fireEvent, render, screen } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import DateInput from "../src/frontend/DateInput.jsx"
import ModelSelector from "../src/frontend/ModelSelector.jsx"

const translations = {
  "date.start": "Start Date",
  "date.end": "End Date",
  "date.quickRange": "Quick range",
  "date.oneMonth": "1M",
  "date.threeMonths": "3M",
  "date.sixMonths": "6M",
  "date.ytd": "YTD",
  "date.oneYear": "1Y",
  "date.fiveYears": "5Y",
  "model.select": "Select AI Model",
  "model.lstm": "LSTM (Neural Network)",
  "model.lightgbm": "LightGBM (Gradient Boosting)",
  "model.arima": "ARIMA (Time Series)",
  "model.arimaTransformer": "ARIMA + Transformer",
  "model.transformer": "Transformer",
  "model.trainingWarningLabel": "Training data warning",
  "model.rangeNote": "Range note",
  "model.insufficientDataWarning": "This range contains fewer than 100 estimated market days. Transformer forecasting may use the lightweight fallback.",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key, fallback) => translations[key] ?? fallback ?? key,
  }),
}))

describe("DateInput quick ranges", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-23T12:00:00"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("updates both dates immediately from each preset", () => {
    const onDateRangeChange = vi.fn()
    render(<DateInput onDateRangeChange={onDateRangeChange} notifyInitial={false} inputIdPrefix="stock-date" />)

    expect(screen.getByLabelText("Start Date")).toHaveValue("2026-04-22")
    expect(screen.getByLabelText("End Date")).toHaveValue("2026-07-22")
    expect(screen.getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "true")

    fireEvent.click(screen.getByRole("button", { name: "1M" }))
    expect(screen.getByLabelText("Start Date")).toHaveValue("2026-06-22")
    expect(onDateRangeChange).toHaveBeenLastCalledWith("2026-06-22", "2026-07-22")

    fireEvent.click(screen.getByRole("button", { name: "6M" }))
    expect(screen.getByLabelText("Start Date")).toHaveValue("2026-01-22")
    expect(onDateRangeChange).toHaveBeenLastCalledWith("2026-01-22", "2026-07-22")

    fireEvent.click(screen.getByRole("button", { name: "1Y" }))
    expect(screen.getByLabelText("Start Date")).toHaveValue("2025-07-22")
    expect(onDateRangeChange).toHaveBeenLastCalledWith("2025-07-22", "2026-07-22")

    fireEvent.click(screen.getByRole("button", { name: "YTD" }))
    expect(screen.getByLabelText("Start Date")).toHaveValue("2026-01-01")
    expect(onDateRangeChange).toHaveBeenLastCalledWith("2026-01-01", "2026-07-22")

    fireEvent.click(screen.getByRole("button", { name: "5Y" }))
    expect(screen.getByLabelText("Start Date")).toHaveValue("2021-07-22")
    expect(onDateRangeChange).toHaveBeenLastCalledWith("2021-07-22", "2026-07-22")
  })
})

describe("ModelSelector training requirement", () => {
  it("shows an accessible range note when Transformer training data is insufficient", () => {
    const { rerender } = render(
      <ModelSelector
        initialModel="TRANSFORMER"
        startDate="2026-06-22"
        endDate="2026-07-22"
      />,
    )

    const warningNote = screen.getByRole("note", { name: "Training data warning" })
    expect(warningNote).toHaveTextContent("Range note")
    expect(warningNote).toHaveAttribute("aria-describedby", "model-training-warning-tooltip")
    expect(screen.getByRole("tooltip")).toHaveTextContent("fewer than 100 estimated market days")
    expect(screen.queryByText("Training data requirement")).not.toBeInTheDocument()

    rerender(
      <ModelSelector
        initialModel="TRANSFORMER"
        startDate="2025-07-22"
        endDate="2026-07-22"
      />,
    )

    expect(screen.queryByRole("note", { name: "Training data warning" })).not.toBeInTheDocument()
  })
})
