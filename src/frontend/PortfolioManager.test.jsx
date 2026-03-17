import "@testing-library/jest-dom"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import i18n from "./config/i18n"
import PortfolioManager from "./PortfolioManager"

// Mock react-plotly.js
vi.mock("react-plotly.js", () => ({
  default: (props) => <div data-testid="plotly-chart" />,
}))

// Mock axios
vi.mock("axios", () => ({
  default: {
    post: vi.fn(),
  },
}))

import axios from "axios"

const renderWithI18n = (component) =>
  render(<I18nextProvider i18n={i18n}>{component}</I18nextProvider>)

describe("PortfolioManager", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders the form with initial holding row and configuration fields", () => {
    renderWithI18n(<PortfolioManager />)
    // Title
    expect(screen.getByText(/Portfolio Manager/i)).toBeInTheDocument()
    // Holding inputs
    const tickerInputs = screen.getAllByPlaceholderText(/e\.g\., AAPL/i)
    expect(tickerInputs.length).toBeGreaterThanOrEqual(1)
    // Configuration selects
    expect(screen.getByLabelText(/Forecast Method/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Optimization Method/i)).toBeInTheDocument()
    // Date fields
    expect(screen.getByLabelText(/Start Date/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/End Date/i)).toBeInTheDocument()
    // Risk-free rate
    expect(screen.getByLabelText(/Risk-Free Rate/i)).toBeInTheDocument()
    // Submit button
    expect(screen.getByText(/Rebalance Portfolio/i)).toBeInTheDocument()
  })

  it("allows adding and removing holdings", async () => {
    renderWithI18n(<PortfolioManager />)
    const user = userEvent.setup()

    // Initially 1 row
    let tickerInputs = screen.getAllByPlaceholderText(/e\.g\., AAPL/i)
    expect(tickerInputs).toHaveLength(1)

    // Add holding
    await user.click(screen.getByText(/\+ Add Holding/i))
    tickerInputs = screen.getAllByPlaceholderText(/e\.g\., AAPL/i)
    expect(tickerInputs).toHaveLength(2)

    // Remove one (× buttons appear when >1 row)
    const removeButtons = screen.getAllByLabelText(/Remove holding/i)
    expect(removeButtons.length).toBe(2)
    await user.click(removeButtons[0])
    tickerInputs = screen.getAllByPlaceholderText(/e\.g\., AAPL/i)
    expect(tickerInputs).toHaveLength(1)
  })

  it("parses holdings input and submits to API correctly", async () => {
    const mockResponse = {
      data: {
        weights: { AAPL: 0.6, MSFT: 0.4 },
        prices: { AAPL: 150, MSFT: 200 },
        buy_list: { MSFT: { quantity: 2, price: 200, value: 400 } },
        sell_list: {},
        total_target_value: 3000,
        expected_return: 0.12,
        volatility: 0.18,
        sharpe_ratio: 0.56,
      },
    }
    axios.post.mockResolvedValueOnce(mockResponse)
    renderWithI18n(<PortfolioManager />)
    const user = userEvent.setup()

    // Fill in a holding
    const tickerInput = screen.getAllByPlaceholderText(/e\.g\., AAPL/i)[0]
    const quantityInput = screen.getAllByPlaceholderText(/e\.g\., 10/i)[0]
    await user.type(tickerInput, "AAPL")
    await user.type(quantityInput, "10")

    // Fill in dates
    fireEvent.change(screen.getByLabelText(/Start Date/i), { target: { value: "2023-01-01" } })
    fireEvent.change(screen.getByLabelText(/End Date/i), { target: { value: "2023-12-31" } })

    // Submit
    await user.click(screen.getByText(/Rebalance Portfolio/i))

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith(
        "http://127.0.0.1:5000/api/manage-portfolio",
        expect.objectContaining({
          current_holdings: { AAPL: 10 },
          cash_injection: 0,
        })
      )
    })
  })

  it("renders buy/sell tables and pie charts after successful response", async () => {
    const mockResponse = {
      data: {
        weights: { AAPL: 0.6, MSFT: 0.4 },
        prices: { AAPL: 150, MSFT: 200 },
        buy_list: { MSFT: { quantity: 2.5, price: 200, value: 500 } },
        sell_list: { AAPL: { quantity: 1, price: 150, value: 150 } },
        total_target_value: 3000,
        expected_return: 0.12,
        volatility: 0.18,
        sharpe_ratio: 0.56,
      },
    }
    axios.post.mockResolvedValueOnce(mockResponse)
    renderWithI18n(<PortfolioManager />)
    const user = userEvent.setup()

    // Fill form
    const tickerInput = screen.getAllByPlaceholderText(/e\.g\., AAPL/i)[0]
    const quantityInput = screen.getAllByPlaceholderText(/e\.g\., 10/i)[0]
    await user.type(tickerInput, "AAPL")
    await user.type(quantityInput, "10")
    fireEvent.change(screen.getByLabelText(/Start Date/i), { target: { value: "2023-01-01" } })
    fireEvent.change(screen.getByLabelText(/End Date/i), { target: { value: "2023-12-31" } })

    await user.click(screen.getByText(/Rebalance Portfolio/i))

    await waitFor(() => {
      // Buy/sell list sections
      expect(screen.getByText("Buy List")).toBeInTheDocument()
      expect(screen.getByText("Sell List")).toBeInTheDocument()
      // Pie charts via mocked Plotly
      const charts = screen.getAllByTestId("plotly-chart")
      expect(charts.length).toBe(2)
      // Metrics
      expect(screen.getByText("12.00%")).toBeInTheDocument()
      expect(screen.getByText("18.00%")).toBeInTheDocument()
      expect(screen.getByText("0.56")).toBeInTheDocument()
    })
  })

  it("displays error message on API failure", async () => {
    axios.post.mockRejectedValueOnce({
      response: { data: { error: "Date range is invalid" } },
    })
    renderWithI18n(<PortfolioManager />)
    const user = userEvent.setup()

    const tickerInput = screen.getAllByPlaceholderText(/e\.g\., AAPL/i)[0]
    const quantityInput = screen.getAllByPlaceholderText(/e\.g\., 10/i)[0]
    await user.type(tickerInput, "AAPL")
    await user.type(quantityInput, "10")
    fireEvent.change(screen.getByLabelText(/Start Date/i), { target: { value: "2023-01-01" } })
    fireEvent.change(screen.getByLabelText(/End Date/i), { target: { value: "2023-12-31" } })

    await user.click(screen.getByText(/Rebalance Portfolio/i))

    await waitFor(() => {
      expect(screen.getByText(/Date range is invalid/i)).toBeInTheDocument()
    })
  })

  it("opens upload CSV modal and closes it", async () => {
    renderWithI18n(<PortfolioManager />)
    const user = userEvent.setup()

    // Click upload button
    await user.click(screen.getByText("Upload Holdings CSV"))
    // Modal title element should appear
    const modalTitle = screen.getByRole("heading", { name: /Upload Holdings/i })
    expect(modalTitle).toBeInTheDocument()

    // Close modal via Close button
    await user.click(screen.getByText("Close"))
    // Modal title should be gone
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: /Upload Holdings/i })).not.toBeInTheDocument()
    })
  })
})
