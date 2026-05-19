import { describe, expect, it } from "vitest"

import {
  buildExportBaseName,
  buildPortfolioExportPayload,
  buildTargetHoldingsCsv,
  escapeCsvValue,
} from "../src/frontend/portfolioManagerExports"

describe("portfolio manager export helpers", () => {
  it("builds stable export names from portfolio ids and timestamps", () => {
    const date = new Date("2026-05-19T03:04:05.678Z")

    expect(buildExportBaseName("My Portfolio #1", date)).toBe(
      "my-portfolio-1-2026-05-19T03-04-05-678Z"
    )
  })

  it("escapes csv values only when needed", () => {
    expect(escapeCsvValue("AAPL")).toBe("AAPL")
    expect(escapeCsvValue('Alpha, "Beta"')).toBe('"Alpha, ""Beta"""')
    expect(escapeCsvValue(null)).toBe("")
  })

  it("exports positive target quantities as sorted benchmark-ready holdings csv", () => {
    const csv = buildTargetHoldingsCsv({
      target_quantities: { MSFT: 0, AAPL: 1.25, TSLA: 2 },
      prices: { AAPL: 200, TSLA: 12.5 },
      weights: { AAPL: 0.6, TSLA: 0.4 },
    })

    expect(csv).toBe(
      [
        "TICKER,QUANTITY,PRICE,MARKET_VALUE,TARGET_WEIGHT",
        "AAPL,1.250000,200.00,250.00,0.60000000",
        "TSLA,2.000000,12.50,25.00,0.40000000",
      ].join("\n")
    )
  })

  it("keeps weights and prices at the top level for benchmark uploads", () => {
    const payload = buildPortfolioExportPayload({
      results: {
        weights: { AAPL: 1 },
        prices: { AAPL: 200 },
        return: 0.12,
        risk: 0.2,
        sharpe_ratio: 0.5,
      },
      managerSettings: { cash_injection: 5000, forecast_method: "LIGHTWEIGHT" },
      portfolioId: "portfolio-rebalance-test",
      exportedAt: "2026-05-19T00:00:00.000Z",
    })

    expect(payload).toMatchObject({
      portfolio_id: "portfolio-rebalance-test",
      export_type: "portfolio_manager_rebalance",
      weights: { AAPL: 1 },
      prices: { AAPL: 200 },
      expected_return: 0.12,
      volatility: 0.2,
      cash_injection: 5000,
      manager_settings: { cash_injection: 5000, forecast_method: "LIGHTWEIGHT" },
    })
  })
})
