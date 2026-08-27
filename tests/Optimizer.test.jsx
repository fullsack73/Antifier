import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"
import { afterEach, describe, expect, it, vi } from "vitest"
import axios from "axios"

import Optimizer from "../src/frontend/Optimizer.jsx"
import { OPTIMIZER_JOB_STORAGE_KEY } from "../src/frontend/optimizerJobStorage.js"
import en from "../src/frontend/locales/en/translation.json"
import ko from "../src/frontend/locales/ko/translation.json"

vi.mock("axios", () => ({
  default: {
    post: vi.fn(),
  },
}))

const translations = {
  "optimizer.kicker": "Portfolio Optimization",
  "optimizer.title": "Portfolio Optimizer",
  "optimizer.loadPortfolio": "Load JSON",
  "optimizer.advancedSettings": "Advanced Settings",
  "optimizer.tickerGroup": "Ticker Group",
  "optimizer.forecastMethod": "Forecast Method",
  "optimizer.optimizationMethod": "Optimization Method",
  "optimizer.lightweight": "Lightweight Prediction",
  "optimizer.ensemble": "ARIMA + Transformer",
  "optimizer.transformer": "Transformer",
  "optimizer.minVariance": "Minimum Variance (Default)",
  "optimizer.minVarianceShort": "Minimum Variance",
  "optimizer.riskOnlyForecast": "Not used (risk-only)",
  "optimizer.bl": "Black-Litterman",
  "optimizer.mpt": "Mean-Variance (MPT)",
  "optimizer.startDate": "Start Date",
  "optimizer.endDate": "End Date",
  "optimizer.riskFreeRate": "Risk-Free Rate (%)",
  "optimizer.targetReturn": "Target Return (%)",
  "optimizer.riskTolerance": "Risk Tolerance (%)",
  "optimizer.submit": "Optimize Portfolio",
  "optimizer.complete": "Optimization complete!",
  "optimizer.results": "Optimized Portfolio",
  "optimizer.return": "Expected Return",
  "optimizer.risk": "Risk (Std. Dev)",
  "optimizer.sharpeRatio": "Sharpe Ratio",
  "optimizer.metricUnavailable": "Unavailable",
  "optimizer.performanceUnavailable": "Performance metrics are unavailable because retained holdings fall outside the modeled universe. Review unmodeled weights before acting.",
  "optimizer.missingAllocationPrices": "Allocation is unavailable because valid prices are missing for: {{tickers}}.",
  "optimizer.investmentBudget": "Investment Budget",
  "optimizer.calculate": "Calculate",
  "optimizer.allocationResults": "Allocation Results",
  "optimizer.weights": "Weights",
  "optimizer.cancel": "Cancel",
  "optimizer.cancelled": "Optimization cancelled",
  "optimizer.backgroundJobNote": "You can leave this screen; the optimizer will reconnect while this app remains open.",
  "common.starting": "Starting...",
  "common.processing": "Processing...",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key, fallback, values = {}) => Object.entries(values).reduce(
      (text, [name, value]) => text.replaceAll(`{{${name}}}`, String(value)),
      translations[key] ?? fallback ?? key,
    ),
  }),
}))

class MockEventSource {
  static instances = []

  constructor(url) {
    this.url = url
    this.listeners = {}
    this.closed = false
    MockEventSource.instances.push(this)
  }

  addEventListener(type, listener) {
    this.listeners[type] = listener
  }

  close() {
    this.closed = true
  }

  emit(type, payload) {
    this.listeners[type]?.({ data: JSON.stringify(payload) })
  }
}

const portfolioResult = {
  weights: { AAPL: 1 },
  return: 0.1,
  risk: 0.2,
  sharpe_ratio: 0.5,
  prices: { AAPL: 100 },
  asset_names: { AAPL: "Apple Inc." },
}

const runningStatus = {
  request_id: "job-running",
  portfolio_id: "job-running",
  status: "running",
  progress: 45,
  message: "Fetching data",
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.localStorage.clear()
  MockEventSource.instances = []
})

describe("Optimizer job lifecycle", () => {
  it("starts optimization with persistent job fields and stores the active job", async () => {
    vi.stubGlobal("EventSource", MockEventSource)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({}),
    }))
    axios.post.mockImplementation((url, payload) => Promise.resolve({
      data: {
        request_id: payload.request_id,
        portfolio_id: payload.portfolio_id,
        status: "running",
        progress: 0,
        message: "Optimization started",
      },
    }))

    render(<Optimizer />)

    fireEvent.change(screen.getByLabelText("Start Date"), { target: { value: "2024-01-01" } })
    fireEvent.change(screen.getByLabelText("End Date"), { target: { value: "2024-03-01" } })
    fireEvent.click(screen.getByRole("button", { name: "Optimize Portfolio" }))

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith("/api/optimize-portfolio", expect.any(Object))
    })

    const payload = axios.post.mock.calls[0][1]
    expect(payload.request_id).toMatch(/^req_/)
    expect(payload.portfolio_id).toBe(payload.request_id)
    expect(payload.persist_result).toBe(true)
    expect(payload.load_if_available).toBe(true)
    expect(payload.optimization_method).toBe("MIN_VARIANCE")
    expect(payload.forecast_method).toBe("RISK_ONLY")

    const stored = JSON.parse(window.localStorage.getItem(OPTIMIZER_JOB_STORAGE_KEY))
    expect(stored.requestId).toBe(payload.request_id)
    expect(stored.portfolioId).toBe(payload.request_id)
    expect(stored.status).toBe("running")
  })

  it("restores a running job and reconnects to its progress stream", async () => {
    vi.stubGlobal("EventSource", MockEventSource)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(runningStatus),
    }))
    window.localStorage.setItem(OPTIMIZER_JOB_STORAGE_KEY, JSON.stringify({
      requestId: "job-running",
      portfolioId: "job-running",
      status: "running",
      startedAt: "2026-07-09T00:00:00Z",
      updatedAt: "2026-07-09T00:00:00Z",
    }))

    render(<Optimizer />)

    await waitFor(() => {
      expect(MockEventSource.instances[0].url).toBe("/api/progress-stream/job-running")
    })
    expect(screen.getByText("45% - Fetching data")).toBeInTheDocument()
  })

  it("renders a completed restored job from the status endpoint", async () => {
    vi.stubGlobal("EventSource", MockEventSource)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        request_id: "job-complete",
        portfolio_id: "job-complete",
        status: "completed",
        progress: 100,
        message: "Optimization complete",
        result: portfolioResult,
      }),
    }))
    window.localStorage.setItem(OPTIMIZER_JOB_STORAGE_KEY, JSON.stringify({
      requestId: "job-complete",
      portfolioId: "job-complete",
      status: "running",
      startedAt: "2026-07-09T00:00:00Z",
      updatedAt: "2026-07-09T00:00:00Z",
    }))

    render(<Optimizer />)

    await waitFor(() => {
      expect(screen.getByText("Optimized Portfolio")).toBeInTheDocument()
    })
    expect(screen.getByText("10.00%")).toBeInTheDocument()
    expect(screen.getByText("AAPL")).toBeInTheDocument()
  })

  it("renders unavailable metrics for retained unmodeled holdings", async () => {
    vi.stubGlobal("EventSource", MockEventSource)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        request_id: "job-unmodeled",
        portfolio_id: "job-unmodeled",
        status: "completed",
        progress: 100,
        message: "Optimization complete",
        result: {
          ...portfolioResult,
          weights: { AAPL: 0.3, OLD: 0.7 },
          return: null,
          risk: null,
          sharpe_ratio: null,
          performance_status: "unavailable_unmodeled_exposure",
          performance_coverage: 0.3,
          unmodeled_weights: { OLD: 0.7 },
        },
      }),
    }))
    window.localStorage.setItem(OPTIMIZER_JOB_STORAGE_KEY, JSON.stringify({
      requestId: "job-unmodeled",
      portfolioId: "job-unmodeled",
      status: "running",
      startedAt: "2026-07-09T00:00:00Z",
      updatedAt: "2026-07-09T00:00:00Z",
    }))

    render(<Optimizer />)

    await waitFor(() => {
      expect(screen.getByText(
        "Performance metrics are unavailable because retained holdings fall outside the modeled universe. Review unmodeled weights before acting.",
      )).toBeInTheDocument()
    })
    expect(screen.getAllByText("Unavailable")).toHaveLength(3)
    expect(screen.getByText("OLD")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Investment Budget"), {
      target: { value: "10000" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Calculate" }))
    await waitFor(() => {
      expect(screen.getByText(
        "Allocation is unavailable because valid prices are missing for: OLD.",
      )).toBeInTheDocument()
      expect(screen.queryByText("Allocation Results")).not.toBeInTheDocument()
    })
  })

  it("sends a cancel request for the restored running job", async () => {
    vi.stubGlobal("EventSource", MockEventSource)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(runningStatus),
    }))
    axios.post.mockResolvedValue({
      data: {
        request_id: "job-running",
        portfolio_id: "job-running",
        status: "cancelled",
        progress: 45,
        message: "Optimization cancelled",
      },
    })
    window.localStorage.setItem(OPTIMIZER_JOB_STORAGE_KEY, JSON.stringify({
      requestId: "job-running",
      portfolioId: "job-running",
      status: "running",
      startedAt: "2026-07-09T00:00:00Z",
      updatedAt: "2026-07-09T00:00:00Z",
    }))

    render(<Optimizer />)

    const cancelButton = await screen.findByRole("button", { name: "Cancel" })
    fireEvent.click(cancelButton)

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith("/api/optimization-jobs/job-running/cancel")
    })
    await waitFor(() => {
      expect(window.localStorage.getItem(OPTIMIZER_JOB_STORAGE_KEY)).toBeNull()
    })
  })

  it("renders advanced controls, converts percent payloads, and manages constraint rows", async () => {
    vi.stubGlobal("EventSource", MockEventSource)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({}),
    }))
    axios.post.mockImplementation((url, payload) => Promise.resolve({
      data: {
        request_id: payload.request_id,
        portfolio_id: payload.portfolio_id,
        status: "running",
        progress: 0,
      },
    }))

    const { container } = render(<Optimizer />)
    const portfolioFile = new File(
      [JSON.stringify({ weights: { AAPL: 0.6, MSFT: 0.4 }, prices: { AAPL: 100, MSFT: 200 } })],
      "current.json",
      { type: "application/json" },
    )
    fireEvent.change(container.querySelector('input[type="file"][accept="application/json"]'), {
      target: { files: [portfolioFile] },
    })
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument())

    fireEvent.click(screen.getByRole("button", { name: "Advanced Settings" }))
    expect(screen.getByLabelText("Target Return (%)")).toBeDisabled()
    expect(screen.getByLabelText("Risk Tolerance (%)")).toBeDisabled()

    fireEvent.change(screen.getByLabelText("Maximum Asset Weight (%)"), { target: { value: "40" } })
    fireEvent.change(screen.getByLabelText("L2 Diversification Gamma"), { target: { value: "0.3" } })
    fireEvent.change(screen.getByLabelText("Minimum Holding Weight (%)"), { target: { value: "5" } })
    fireEvent.change(screen.getByLabelText("Turnover Penalty"), { target: { value: "0.15" } })
    fireEvent.change(screen.getByLabelText("Rebalance Band (%)"), { target: { value: "2" } })
    fireEvent.change(screen.getByLabelText("Maximum Turnover (%)"), { target: { value: "35" } })

    fireEvent.click(screen.getByRole("button", { name: "Add asset" }))
    fireEvent.change(screen.getByLabelText("Asset constraint ticker"), { target: { value: "AAPL" } })
    fireEvent.change(screen.getByLabelText("Asset minimum percent"), { target: { value: "10" } })
    fireEvent.change(screen.getByLabelText("Asset maximum percent"), { target: { value: "30" } })

    fireEvent.click(screen.getByRole("button", { name: "Add group" }))
    fireEvent.change(screen.getByLabelText("Group dimension"), { target: { value: "sector" } })
    fireEvent.change(screen.getByLabelText("Group name"), { target: { value: "Technology" } })
    fireEvent.change(screen.getByLabelText("Group minimum percent"), { target: { value: "20" } })
    fireEvent.change(screen.getByLabelText("Group maximum percent"), { target: { value: "60" } })

    fireEvent.click(screen.getByRole("button", { name: "Done" }))
    fireEvent.change(screen.getByLabelText("Start Date"), { target: { value: "2026-01-01" } })
    fireEvent.change(screen.getByLabelText("End Date"), { target: { value: "2026-08-20" } })
    fireEvent.click(screen.getByRole("button", { name: "Optimize Portfolio" }))

    await waitFor(() => expect(axios.post).toHaveBeenCalled())
    const payload = axios.post.mock.calls.at(-1)[1]
    expect(payload.max_asset_weight).toBe(0.4)
    expect(payload.l2_gamma).toBe(0.3)
    expect(payload.min_holding_weight).toBe(0.05)
    expect(payload.current_weights).toEqual({ AAPL: 0.6, MSFT: 0.4 })
    expect(payload.turnover_penalty).toBe(0.15)
    expect(payload.rebalance_band).toBe(0.02)
    expect(payload.max_turnover).toBe(0.35)
    expect(payload.asset_constraints).toEqual([
      { ticker: "AAPL", min_weight: 0.1, max_weight: 0.3 },
    ])
    expect(payload.group_constraints).toEqual([
      { dimension: "sector", group: "Technology", min_weight: 0.2, max_weight: 0.6 },
    ])
  })

  it("prevents empty constraints and supports removing rows", () => {
    render(<Optimizer />)
    fireEvent.click(screen.getByRole("button", { name: "Advanced Settings" }))
    fireEvent.click(screen.getByRole("button", { name: "Add asset" }))
    expect(screen.getByLabelText("Asset constraint ticker")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Remove asset constraint" }))
    expect(screen.queryByLabelText("Asset constraint ticker")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Add group" }))
    fireEvent.click(screen.getByRole("button", { name: "Done" }))
    fireEvent.change(screen.getByLabelText("Start Date"), { target: { value: "2026-01-01" } })
    fireEvent.change(screen.getByLabelText("End Date"), { target: { value: "2026-08-20" } })
    fireEvent.click(screen.getByRole("button", { name: "Optimize Portfolio" }))
    expect(screen.getByText("Complete or remove every constraint row before running.")).toBeInTheDocument()
  })

  it("renders structured constraint validation details from a failed job", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        request_id: "job-infeasible",
        portfolio_id: "job-infeasible",
        status: "failed",
        progress: 0,
        error: "The requested cap is infeasible.",
        error_details: {
          error_code: "MAX_ASSET_WEIGHT_INFEASIBLE",
          constraint: "max_asset_weight",
          feasible_bound: { minimum: 0.25 },
          affected_tickers: ["AAPL", "MSFT"],
          affected_groups: [],
        },
      }),
    }))
    window.localStorage.setItem(OPTIMIZER_JOB_STORAGE_KEY, JSON.stringify({
      requestId: "job-infeasible",
      portfolioId: "job-infeasible",
      status: "running",
    }))

    render(<Optimizer />)

    expect(await screen.findByText("The requested cap is infeasible.")).toBeInTheDocument()
    expect(screen.getByText(/MAX_ASSET_WEIGHT_INFEASIBLE/)).toBeInTheDocument()
    expect(screen.getByText(/max_asset_weight/)).toBeInTheDocument()
    expect(screen.getByText(/AAPL, MSFT/)).toBeInTheDocument()
  })

  it("renders diagnostics, binding state, and metadata availability", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        request_id: "job-diagnostics",
        portfolio_id: "job-diagnostics",
        status: "completed",
        progress: 100,
        result: {
          ...portfolioResult,
          risk_diagnostics: {
            status: "complete",
            concentration: { hhi: 1, effective_number_of_holdings: 1, maximum_asset_weight: 1 },
            covariance: { condition_number: 4, effective_rank: 1, average_pairwise_correlation: null },
            risk_contributions: {
              AAPL: { percentage_risk_contribution: 1 },
            },
          },
          constraint_diagnostics: {
            all_satisfied: true,
            constraints: [{
              constraint: "max_asset_weight",
              actual_value: 1,
              lower_bound: null,
              upper_bound: 1,
              binding: true,
              satisfied: true,
            }],
          },
          classification_metadata: { status: "partial" },
        },
      }),
    }))
    window.localStorage.setItem(OPTIMIZER_JOB_STORAGE_KEY, JSON.stringify({
      requestId: "job-diagnostics",
      portfolioId: "job-diagnostics",
      status: "running",
    }))

    render(<Optimizer />)
    expect(await screen.findByText("Concentration & covariance")).toBeInTheDocument()
    expect(screen.getByText("Constraints satisfied")).toBeInTheDocument()
    expect(screen.getByText("Binding")).toBeInTheDocument()
    expect(screen.getByText("Metadata: partial")).toBeInTheDocument()
    expect(screen.getByText("Risk by asset")).toBeInTheDocument()
  })

  it("keeps English and Korean constraint translation keys aligned", () => {
    const keys = [
      "maxAssetWeight",
      "assetOverrides",
      "groupConstraints",
      "constraintsSatisfied",
      "riskContribution",
      "metadataStatus",
    ]
    for (const key of keys) {
      expect(en.optimizer[key]).toBeTruthy()
      expect(ko.optimizer[key]).toBeTruthy()
    }
  })
})
