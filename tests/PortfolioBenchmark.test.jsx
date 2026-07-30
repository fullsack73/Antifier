import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"
import { afterEach, describe, expect, it, vi } from "vitest"

import axios from "axios"
import PortfolioBenchmark from "../src/frontend/PortfolioBenchmark.jsx"

const translations = {
  "benchmark.kicker": "Performance Benchmark",
  "benchmark.title": "Portfolio Benchmark",
  "benchmark.subtitle": "Compare one allocation.",
  "benchmark.comparisonSet": "Comparison set",
  "benchmark.primarySeries": "Primary series",
  "benchmark.marketReference": "Market reference",
  "benchmark.baseline": "Cash baseline",
  "benchmark.sourceTitle": "Portfolio source",
  "benchmark.sourceDescription": "Load an exported portfolio.",
  "benchmark.parametersTitle": "Analysis parameters",
  "benchmark.parametersDescription": "Set shared inputs.",
  "benchmark.uploadPortfolio": "Portfolio File",
  "benchmark.chooseFile": "Choose Portfolio JSON",
  "benchmark.portfolioLoaded": "Portfolio Loaded",
  "benchmark.fileFormat": "JSON with weights and prices",
  "benchmark.assetsReady": "{{count}} assets ready for analysis",
  "benchmark.sourceNoteLabel": "File contract",
  "benchmark.sourceNote": "Use an Antifier export.",
  "benchmark.budget": "Investment Budget",
  "benchmark.budgetHint": "Starting value in USD",
  "benchmark.riskFreeRate": "Risk-Free Rate (%)",
  "benchmark.riskFreeHint": "Annual percentage",
  "benchmark.readyTitle": "Inputs ready",
  "benchmark.readyHint": "Run comparison.",
  "benchmark.notReadyTitle": "Complete the setup",
  "benchmark.notReadyHint": "Add required inputs.",
  "benchmark.analyze": "Analyze Portfolio",
  "benchmark.portfolio": "Portfolio",
  "benchmark.sp500": "S&P 500",
  "benchmark.riskFree": "Risk-Free Asset",
  "common.loading": "Loading",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key, options) => {
      const value = translations[key] ?? (typeof options === "string" ? options : key)
      return typeof options === "object"
        ? value.replace("{{count}}", String(options.count))
        : value
    },
  }),
}))

vi.mock("../src/frontend/DateInput.jsx", () => ({
  default: ({ onDateRangeChange }) => (
    <button type="button" onClick={() => onDateRangeChange("2025-01-01", "2025-12-31")}>
      Set date range
    </button>
  ),
}))

vi.mock("../src/frontend/BenchmarkChart.jsx", () => ({
  default: () => <div>Benchmark chart</div>,
}))

vi.mock("../src/frontend/BenchmarkResultsTable.jsx", () => ({
  default: () => <div>Benchmark summary</div>,
}))

vi.mock("../src/frontend/SkeletonScreens.jsx", () => ({
  BenchmarkSkeleton: () => <div>Loading benchmark</div>,
}))

vi.mock("axios", () => ({
  default: {
    post: vi.fn(),
  },
}))

afterEach(() => {
  vi.clearAllMocks()
})

describe("PortfolioBenchmark", () => {
  it("enables analysis after a valid portfolio and shared inputs are ready", async () => {
    axios.post.mockResolvedValue({
      data: {
        portfolio_timeline: {},
        sp500_timeline: {},
        riskfree_timeline: {},
        summary: {},
      },
    })

    const { container } = render(<PortfolioBenchmark />)

    const analyzeButton = screen.getByRole("button", { name: "Analyze Portfolio" })
    expect(analyzeButton).toBeDisabled()

    const portfolioFile = new File(
      [
        JSON.stringify({
          portfolio_id: "balanced-core",
          weights: { AAPL: 0.6, MSFT: 0.4 },
          prices: { AAPL: 200, MSFT: 400 },
        }),
      ],
      "balanced-core.json",
      { type: "application/json" },
    )

    fireEvent.change(container.querySelector("#benchmark-portfolio-file"), {
      target: { files: [portfolioFile] },
    })

    await waitFor(() => {
      expect(screen.getByText("balanced-core")).toBeInTheDocument()
    })

    expect(screen.getByText("2 assets ready for analysis")).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Investment Budget"), {
      target: { value: "25000" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Set date range" }))

    expect(analyzeButton).toBeEnabled()
    fireEvent.click(analyzeButton)

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith("/api/benchmark-portfolio", {
        portfolio_data: expect.objectContaining({ portfolio_id: "balanced-core" }),
        budget: 25000,
        start_date: "2025-01-01",
        end_date: "2025-12-31",
        risk_free_rate: 0.04,
      })
    })
  })
})
