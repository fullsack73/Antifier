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
})
