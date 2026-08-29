import { describe, expect, it } from "vitest"

import {
  buildExportBaseName,
  buildPortfolioExportPayload,
  buildTargetHoldingsCsv,
  escapeCsvValue,
  parseImportedTarget,
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
      execution_target_weights: { AAPL: 0.5, TSLA: 0.05 },
    })

    expect(csv).toBe(
      [
        "TICKER,QUANTITY,PRICE,MARKET_VALUE,TARGET_WEIGHT",
        "AAPL,1.250000,200.00,250.00,0.50000000",
        "TSLA,2.000000,12.50,25.00,0.05000000",
      ].join("\n")
    )
  })

  it("keeps weights and prices at the top level for benchmark uploads", () => {
    const payload = buildPortfolioExportPayload({
      results: {
        weights: { AAPL: 1 },
        execution_target_weights: { AAPL: 0.99 },
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
      weights: { AAPL: 0.99 },
      prices: { AAPL: 200 },
      expected_return: 0.12,
      volatility: 0.2,
      cash_injection: 5000,
      manager_settings: { cash_injection: 5000, forecast_method: "LIGHTWEIGHT" },
    })
  })

  it("imports optimizer, manager, and compatible top-level weights without stale state", () => {
    const imported = parseImportedTarget({
      portfolio_id: "gmv-six-months-ago",
      exported_at: "2026-02-01T00:00:00Z",
      weights: { AAPL: 0.5, MSFT: 0.3 },
      prices: { AAPL: 1 },
      current_holdings: { OLD: 999 },
      buy_list: { OLD: {} },
    }, "optimizer.json")

    expect(imported).toMatchObject({
      weights: { AAPL: 0.5, MSFT: 0.3 },
      assetCount: 2,
      fileName: "optimizer.json",
      portfolioId: "gmv-six-months-ago",
    })
    expect(imported.targetCashWeight).toBeCloseTo(0.2)
    expect(imported).not.toHaveProperty("prices")
    expect(imported).not.toHaveProperty("current_holdings")
  })

  it("rejects duplicate aliases, invalid values, empty weights, and meaningful overflow", () => {
    expect(() => parseImportedTarget({ weights: {} })).toThrow("must not be empty")
    expect(() => parseImportedTarget({ weights: { "BRK.B": 0.5, "BRK-B": 0.5 } })).toThrow("duplicate ticker BRK-B")
    expect(() => parseImportedTarget({ weights: { AAPL: -0.1 } })).toThrow("finite and non-negative")
    expect(() => parseImportedTarget({ weights: { AAPL: true } })).toThrow("finite and non-negative")
    expect(() => parseImportedTarget({ weights: { "BAD TICKER": 0.5 } })).toThrow("invalid ticker")
    expect(() => parseImportedTarget({ weights: { AAPL: 1.001 } })).toThrow("100% or less")
    expect(parseImportedTarget({ weights: { AAPL: 1 + 5e-9 } }).weights.AAPL).toBeCloseTo(1)
  })

  it("round-trips a portfolio manager export through the common target parser", () => {
    const payload = buildPortfolioExportPayload({
      results: {
        calculation_mode: "FIXED_TARGET",
        execution_target_weights: { AAPL: 0.75 },
        target_weights_sha256: "abc123",
        imported_target: { portfolio_id: "original-target" },
      },
      managerSettings: {},
      portfolioId: "manager-result",
    })

    const imported = parseImportedTarget(payload, "manager-result.json")
    expect(imported.weights).toEqual({ AAPL: 0.75 })
    expect(imported.targetCashWeight).toBe(0.25)
    expect(payload.calculation_mode).toBe("FIXED_TARGET")
    expect(payload.target_weights_sha256).toBe("abc123")
  })
})
