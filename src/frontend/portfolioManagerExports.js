const DEFAULT_EXPORT_PREFIX = "portfolio-rebalance"
export const TARGET_WEIGHT_SUM_TOLERANCE = 1e-8

const YAHOO_TICKER_ALIASES = {
  "BF.A": "BF-A",
  "BF.B": "BF-B",
  "BRK.A": "BRK-A",
  "BRK.B": "BRK-B",
}

const normalizeTargetTicker = (value) => {
  const ticker = String(value || "").trim().toUpperCase()
  return YAHOO_TICKER_ALIASES[ticker] || ticker
}

export const parseImportedTarget = (value, fileName = "") => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Portfolio JSON must be an object.")
  }
  if (!value.weights || typeof value.weights !== "object" || Array.isArray(value.weights)) {
    throw new Error("Portfolio JSON must contain a weights object.")
  }

  const entries = Object.entries(value.weights)
  if (entries.length === 0) throw new Error("Portfolio weights must not be empty.")

  const weights = {}
  for (const [rawTicker, rawWeight] of entries) {
    const ticker = normalizeTargetTicker(rawTicker)
    if (!ticker) throw new Error("Portfolio weights contain an empty ticker.")
    if (!/^[A-Z0-9.^=-]{1,24}$/.test(ticker)) {
      throw new Error(`Portfolio weights contain invalid ticker ${ticker}.`)
    }
    if (Object.hasOwn(weights, ticker)) {
      throw new Error(`Portfolio weights contain duplicate ticker ${ticker}.`)
    }
    const weight = typeof rawWeight === "boolean" ? Number.NaN : Number(rawWeight)
    if (!Number.isFinite(weight) || weight < 0) {
      throw new Error(`Weight for ${ticker} must be finite and non-negative.`)
    }
    weights[ticker] = weight
  }

  const total = Object.values(weights).reduce((sum, weight) => sum + weight, 0)
  if (total > 1 + TARGET_WEIGHT_SUM_TOLERANCE) {
    throw new Error("Portfolio weights must sum to 100% or less.")
  }
  if (total > 1) {
    for (const ticker of Object.keys(weights)) weights[ticker] /= total
  }
  const normalizedTotal = Object.values(weights).reduce((sum, weight) => sum + weight, 0)

  return {
    weights,
    targetCashWeight: Math.max(0, 1 - normalizedTotal),
    assetCount: Object.keys(weights).length,
    fileName,
    portfolioId: value.portfolio_id ? String(value.portfolio_id) : "",
    exportedAt: value.exported_at ? String(value.exported_at) : "",
    exportType: value.export_type ? String(value.export_type) : "",
  }
}

const sanitizeFilenamePart = (value) =>
  String(value || DEFAULT_EXPORT_PREFIX)
    .trim()
    .replace(/[^a-z0-9_-]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase() || DEFAULT_EXPORT_PREFIX

export const buildExportBaseName = (portfolioId, now = new Date()) => {
  const timestamp = now.toISOString().replace(/[:.]/g, "-")
  return `${sanitizeFilenamePart(portfolioId)}-${timestamp}`
}

export const escapeCsvValue = (value) => {
  if (value === null || value === undefined) return ""

  const text = String(value)
  if (!/[",\r\n]/.test(text)) return text

  return `"${text.replace(/"/g, '""')}"`
}

export const buildTargetHoldingsCsv = (results) => {
  const quantities = results?.target_quantities || {}
  const prices = results?.prices || {}
  const weights = results?.execution_target_weights || results?.weights || {}

  const rows = Object.entries(quantities)
    .map(([ticker, quantity]) => {
      const numericQuantity = Number(quantity)
      const price = Number(prices[ticker])
      const targetWeight = Number(weights[ticker])

      if (!ticker || !Number.isFinite(numericQuantity) || numericQuantity <= 0) {
        return null
      }

      return {
        ticker,
        quantity: numericQuantity,
        price: Number.isFinite(price) ? price : 0,
        marketValue: Number.isFinite(price) ? numericQuantity * price : 0,
        targetWeight: Number.isFinite(targetWeight) ? targetWeight : 0,
      }
    })
    .filter(Boolean)
    .sort((a, b) => a.ticker.localeCompare(b.ticker))

  const header = "TICKER,QUANTITY,PRICE,MARKET_VALUE,TARGET_WEIGHT"
  const body = rows.map((row) =>
    [
      row.ticker,
      row.quantity.toFixed(6),
      row.price.toFixed(2),
      row.marketValue.toFixed(2),
      row.targetWeight.toFixed(8),
    ]
      .map(escapeCsvValue)
      .join(",")
  )

  return [header, ...body].join("\n")
}

export const buildPortfolioExportPayload = ({
  results,
  managerSettings,
  portfolioId,
  exportedAt = new Date().toISOString(),
}) => {
  if (!results) return null

  return {
    ...results,
    portfolio_id: portfolioId,
    export_type: "portfolio_manager_rebalance",
    exported_at: exportedAt,
    weights: results.execution_target_weights || results.weights || {},
    prices: results.prices || {},
    current_holdings: results.current_holdings || {},
    target_quantities: results.target_quantities || {},
    buy_list: results.buy_list || {},
    sell_list: results.sell_list || {},
    cash_injection: results.cash_injection ?? managerSettings?.cash_injection ?? 0,
    total_target_value: results.total_target_value ?? null,
    remaining_cash: results.remaining_cash ?? null,
    expected_return: results.expected_return ?? results.return ?? null,
    volatility: results.volatility ?? results.risk ?? null,
    sharpe_ratio: results.sharpe_ratio ?? null,
    manager_settings: managerSettings || {},
  }
}

export const downloadBlob = (filename, content, mimeType) => {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")

  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
