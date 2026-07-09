import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"
import { afterEach, describe, expect, it, vi } from "vitest"
import axios from "axios"

import Optimizer from "../src/frontend/Optimizer.jsx"
import { OPTIMIZER_JOB_STORAGE_KEY } from "../src/frontend/optimizerJobStorage.js"

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
  "optimizer.bl": "Black-Litterman",
  "optimizer.mpt": "Mean-Variance (MPT)",
  "optimizer.startDate": "Start Date",
  "optimizer.endDate": "End Date",
  "optimizer.riskFreeRate": "Risk-Free Rate (%)",
  "optimizer.submit": "Optimize Portfolio",
  "optimizer.complete": "Optimization complete!",
  "optimizer.results": "Optimized Portfolio",
  "optimizer.return": "Expected Return",
  "optimizer.risk": "Risk (Std. Dev)",
  "optimizer.sharpeRatio": "Sharpe Ratio",
  "optimizer.weights": "Weights",
  "optimizer.cancel": "Cancel",
  "optimizer.cancelled": "Optimization cancelled",
  "optimizer.backgroundJobNote": "You can leave this screen; the optimizer will reconnect while this app remains open.",
  "common.starting": "Starting...",
  "common.processing": "Processing...",
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key, fallback) => translations[key] ?? fallback ?? key,
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
})
