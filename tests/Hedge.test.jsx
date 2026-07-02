import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"
import { afterEach, describe, expect, it, vi } from "vitest"

import HedgeAnalysis from "../src/frontend/Hedge.jsx"


const translations = {
  "hedge.kicker": "Pairs analysis",
  "hedge.title": "Pairs / Correlation Analysis",
  "hedge.label1": "First Ticker",
  "hedge.label2": "Second Ticker",
  "hedge.companies": "Companies",
  "hedge.correlationSignal": "Correlation Signal",
  "hedge.statisticalAnalysis": "Statistical Analysis",
  "hedge.analysisPeriod": "Analysis Period",
  "hedge.correlation": "Correlation",
  "hedge.pValue": "P-value",
  "hedge.strength": "Strength",
  "hedge.observations": "Observations",
  "hedge.regression": "Regression",
  "hedge.alpha": "Alpha",
  "hedge.beta": "Beta",
  "hedge.rSquared": "R-squared",
  "hedge.results": "Results",
  "hedge.loadingAnalysis": "Loading pairs analysis",
  "date.start": "Start Date",
  "date.end": "End Date",
  "common.submit": "Submit",
  "common.loading": "Loading...",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key, fallback) => translations[key] ?? fallback ?? key,
  }),
}))

afterEach(() => {
  vi.restoreAllMocks()
})

describe("HedgeAnalysis", () => {
  it("renders pairs analysis metrics from the analyze-hedge API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      json: () => Promise.resolve({
        analysis_type: "pairs_correlation_regression",
        company1: "Apple Inc.",
        company2: "Microsoft Corporation",
        ticker1: "AAPL",
        ticker2: "MSFT",
        period: { start: "2024-01-02", end: "2024-03-15" },
        observations: 35,
        correlation: -0.75234,
        p_value: 0.01234,
        strength: "Strong",
        correlation_signal: {
          direction: "Negative",
          strength: "Strong",
          summary: "The pair has a negative return relationship over this period.",
        },
        regression: {
          alpha: 0.00012,
          beta: -0.61,
          r_squared: 0.82,
          p_value: 0.01234,
          standard_error: 0.04,
        },
      }),
    }))

    render(<HedgeAnalysis />)

    fireEvent.change(screen.getByLabelText("First Ticker"), { target: { value: "aapl" } })
    fireEvent.change(screen.getByLabelText("Second Ticker"), { target: { value: "msft" } })
    fireEvent.click(screen.getByRole("button", { name: "Submit" }))

    await waitFor(() => {
      expect(screen.getByText("Negative")).toBeInTheDocument()
    })

    expect(global.fetch).toHaveBeenCalledWith("/api/analyze-hedge?ticker1=AAPL&ticker2=MSFT")
    expect(screen.getByText("Apple Inc. (AAPL)")).toBeInTheDocument()
    expect(screen.getByText("Microsoft Corporation (MSFT)")).toBeInTheDocument()
    expect(screen.getByText("-0.752")).toBeInTheDocument()
    expect(screen.getByText("-0.610")).toBeInTheDocument()
    expect(screen.getByText("0.820")).toBeInTheDocument()
    expect(screen.queryByText("Yes")).not.toBeInTheDocument()
    expect(screen.queryByText("No")).not.toBeInTheDocument()
  })
})
