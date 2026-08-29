import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"
import { afterEach, expect, it, vi } from "vitest"
import axios from "axios"

import PortfolioManager from "../src/frontend/PortfolioManager.jsx"


vi.mock("axios", () => ({ default: { post: vi.fn() } }))
vi.mock("../src/frontend/LazyPlot.jsx", () => ({ default: () => null }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key, fallback) => fallback || key,
  }),
}))


afterEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  window.localStorage.clear()
})


it("sends meaningful manager optimizer and turnover controls with decimal units", async () => {
  axios.post.mockResolvedValue({ data: { weights: { AAPL: 1 }, prices: { AAPL: 100 } } })
  render(<PortfolioManager />)

  fireEvent.change(screen.getByPlaceholderText("e.g., AAPL"), { target: { value: "AAPL" } })
  fireEvent.change(screen.getByPlaceholderText("e.g., 10"), { target: { value: "10" } })
  fireEvent.change(screen.getByLabelText("Start Date"), { target: { value: "2026-01-01" } })
  fireEvent.change(screen.getByLabelText("End Date"), { target: { value: "2026-08-20" } })
  fireEvent.click(screen.getByRole("button", { name: "Advanced Settings" }))

  fireEvent.change(screen.getByLabelText("Maximum Asset Weight (%)"), { target: { value: "40" } })
  fireEvent.change(screen.getByLabelText("L2 Diversification Gamma"), { target: { value: "0.2" } })
  fireEvent.change(screen.getByLabelText("Minimum Holding Weight (%)"), { target: { value: "5" } })
  fireEvent.change(screen.getByLabelText("Turnover Penalty"), { target: { value: "0.1" } })
  fireEvent.change(screen.getByLabelText("Rebalance Band (%)"), { target: { value: "3" } })
  fireEvent.change(screen.getByLabelText("Maximum Turnover (%)"), { target: { value: "25" } })
  fireEvent.click(screen.getByRole("button", { name: "Done" }))
  fireEvent.click(screen.getByRole("button", { name: "Rebalance Portfolio" }))

  await waitFor(() => expect(axios.post).toHaveBeenCalled())
  const payload = axios.post.mock.calls[0][1]
  expect(payload.max_asset_weight).toBe(0.4)
  expect(payload.l2_gamma).toBe(0.2)
  expect(payload.min_holding_weight).toBe(0.05)
  expect(payload.turnover_penalty).toBe(0.1)
  expect(payload.rebalance_band).toBe(0.03)
  expect(payload.max_turnover).toBe(0.25)
  expect(payload.calculation_mode).toBe("REOPTIMIZE")
})


it("imports fixed weights without applying stale holdings or prices", async () => {
  axios.post.mockResolvedValue({
    data: {
      calculation_mode: "FIXED_TARGET",
      weights: { AAPL: 0.8 },
      execution_target_weights: { AAPL: 0.8 },
      prices: { AAPL: 200 },
      current_holdings: { AAPL: 2 },
      buy_list: {},
      sell_list: {},
      total_target_value: 400,
      target_cash_weight: 0.2,
      target_weights_sha256: "0123456789abcdef",
      imported_target: { portfolio_id: "old-gmv" },
      gross_turnover: 0,
    },
  })
  const { container } = render(<PortfolioManager />)

  fireEvent.click(screen.getByRole("radio", { name: /Rebalance to Imported Target Weights/ }))
  expect(screen.getByRole("button", { name: "Rebalance Portfolio" })).toBeDisabled()

  const file = new File([
    JSON.stringify({
      portfolio_id: "old-gmv",
      weights: { AAPL: 0.8 },
      prices: { AAPL: 5 },
      current_holdings: { OLD: 999 },
      buy_list: { OLD: { quantity: 1 } },
    }),
  ], "old-gmv.json", { type: "application/json" })
  fireEvent.change(container.querySelector('input[type="file"][accept=".json,application/json"]'), {
    target: { files: [file] },
  })

  await screen.findByText("old-gmv")
  fireEvent.change(screen.getByPlaceholderText("e.g., AAPL"), { target: { value: "AAPL" } })
  fireEvent.change(screen.getByPlaceholderText("e.g., 10"), { target: { value: "2" } })
  fireEvent.click(screen.getByRole("button", { name: "Rebalance Portfolio" }))

  await waitFor(() => expect(axios.post).toHaveBeenCalled())
  const payload = axios.post.mock.calls[0][1]
  expect(payload).toMatchObject({
    calculation_mode: "FIXED_TARGET",
    current_holdings: { AAPL: 2 },
    target_weights: { AAPL: 0.8 },
    imported_target: { file_name: "old-gmv.json", portfolio_id: "old-gmv" },
  })
  expect(payload).not.toHaveProperty("prices")
  expect(payload).not.toHaveProperty("start_date")
  expect(payload.current_holdings).not.toHaveProperty("OLD")
  expect(await screen.findByText("Proposal only. No orders are submitted.")).toBeInTheDocument()
  expect(screen.getByText(/0123456789ab/)).toBeInTheDocument()
  expect(screen.queryByText("Expected Return")).not.toBeInTheDocument()
})


it("keeps the previous imported target when replacement JSON is invalid", async () => {
  const { container } = render(<PortfolioManager />)
  fireEvent.click(screen.getByRole("radio", { name: /Rebalance to Imported Target Weights/ }))
  const input = container.querySelector('input[type="file"][accept=".json,application/json"]')
  fireEvent.change(input, {
    target: { files: [new File([JSON.stringify({ portfolio_id: "valid", weights: { AAPL: 1 } })], "valid.json")] },
  })
  await screen.findByText("valid")

  fireEvent.change(input, {
    target: { files: [new File(["not-json"], "broken.json")] },
  })

  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument())
  expect(screen.getByText("valid")).toBeInTheDocument()
  expect(screen.getByText("1")).toBeInTheDocument()
})
