const DEFAULT_EXPORT_PREFIX = "portfolio-rebalance"

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
  const weights = results?.weights || {}

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
    weights: results.weights || {},
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
