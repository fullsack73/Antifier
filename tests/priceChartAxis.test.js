import { describe, expect, it } from "vitest"

import {
  getCurrencyPair,
  getPriceAxisLayout,
  invertCurrencySeries,
  PRICE_NUMBER_FORMAT,
} from "../src/frontend/priceChartAxis.js"

describe("currency pair display", () => {
  it("parses Yahoo FX symbols and safely inverts prices and forecast bounds", () => {
    expect(getCurrencyPair("KRW=X")).toEqual({ base: "USD", quote: "KRW" })
    expect(getCurrencyPair("EURUSD=X")).toEqual({ base: "EUR", quote: "USD" })
    expect(getCurrencyPair("AAPL")).toBeNull()
    expect(invertCurrencySeries({
      "2026-09-01": { mean: 2, min: 1, max: 4 },
    })).toEqual({
      "2026-09-01": { mean: 0.5, min: 0.25, max: 1 },
    })
  })
})

describe("price chart axis", () => {
  it("keeps decimal labels and pads values that differ only by floating-point noise", () => {
    const layout = getPriceAxisLayout([1, 0.9999999999999999])

    expect(layout.tickformat).toBe(PRICE_NUMBER_FORMAT)
    expect(layout.range).toEqual([0.99, 1.01])
  })

  it("leaves meaningful sub-unit price changes on autorange", () => {
    expect(getPriceAxisLayout([0.0012, 0.0014])).toEqual({
      tickformat: PRICE_NUMBER_FORMAT,
    })
  })
})
