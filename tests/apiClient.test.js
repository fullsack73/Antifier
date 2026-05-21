import { describe, expect, it } from "vitest"

import { apiUrl } from "../src/frontend/apiClient"

describe("apiUrl", () => {
  it("builds relative API URLs with encoded query params", () => {
    expect(
      apiUrl("/api/get-data", {
        ticker: "BRK-B",
        regression: true,
        future_days: 30,
        empty: "",
      })
    ).toBe("/api/get-data?ticker=BRK-B&regression=true&future_days=30")
  })

  it("normalizes paths without a leading slash", () => {
    expect(apiUrl("api/asset-names", { ticker: "005930.KS" })).toBe(
      "/api/asset-names?ticker=005930.KS"
    )
  })
})
