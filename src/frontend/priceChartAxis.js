export const PRICE_NUMBER_FORMAT = ",.6~g"

export function getCurrencyPair(ticker) {
  const symbol = String(ticker || "").toUpperCase().replace(/=X$/, "")
  if (!String(ticker || "").toUpperCase().endsWith("=X") || !/^[A-Z]{3}([A-Z]{3})?$/.test(symbol)) return null

  return symbol.length === 3
    ? { base: "USD", quote: symbol }
    : { base: symbol.slice(0, 3), quote: symbol.slice(3) }
}

const inverse = (value) => {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) && numericValue !== 0 ? 1 / numericValue : value
}

export function invertCurrencySeries(data = {}) {
  return Object.fromEntries(Object.entries(data || {}).map(([date, value]) => {
    if (!value || typeof value !== "object") return [date, inverse(value)]

    return [date, {
      ...value,
      mean: inverse(value.mean),
      min: inverse(value.max),
      max: inverse(value.min),
    }]
  }))
}

export function getPriceAxisLayout(values = []) {
  const finiteValues = values.map(Number).filter(Number.isFinite)
  if (finiteValues.length === 0) return { tickformat: PRICE_NUMBER_FORMAT }

  const minimum = Math.min(...finiteValues)
  const maximum = Math.max(...finiteValues)
  const magnitude = Math.max(Math.abs(minimum), Math.abs(maximum))
  const tolerance = Math.max(1, magnitude) * Number.EPSILON * 100

  if (maximum - minimum > tolerance) return { tickformat: PRICE_NUMBER_FORMAT }

  const center = (minimum + maximum) / 2
  const padding = Math.max(magnitude * 0.01, 1e-6)

  return {
    tickformat: PRICE_NUMBER_FORMAT,
    range: [Math.max(0, center - padding), center + padding],
  }
}
