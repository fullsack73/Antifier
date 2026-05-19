export const getSecurityDisplayName = (ticker, results) => {
  const normalizedTicker = String(ticker || "").toUpperCase()
  const assetNames = results?.asset_names || results?.ticker_names || results?.company_names || {}

  return assetNames[ticker] || assetNames[normalizedTicker] || ticker
}

export const formatSecurityDisplay = (ticker, results, displayMode) => {
  if (displayMode === "name") {
    return getSecurityDisplayName(ticker, results)
  }

  return ticker
}

export const fetchSecurityNames = async (tickers) => {
  const uniqueTickers = Array.from(new Set((tickers || []).filter(Boolean).map(ticker => String(ticker).toUpperCase())))
  if (uniqueTickers.length === 0) return {}

  try {
    const response = await fetch("http://127.0.0.1:5000/api/asset-names", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: uniqueTickers }),
    })

    if (response.ok) {
      const data = await response.json()
      if (data?.asset_names) return data.asset_names
    }
  } catch {
    // Fall back to the older stock-data endpoint below for running backends that
    // have not picked up /api/asset-names yet.
  }

  const namePairs = await Promise.all(
    uniqueTickers.map(async (ticker) => {
      try {
        const response = await fetch(`http://127.0.0.1:5000/get-data?ticker=${encodeURIComponent(ticker)}`)
        if (!response.ok) return [ticker, ticker]

        const data = await response.json()
        return [ticker, data?.companyName || ticker]
      } catch {
        return [ticker, ticker]
      }
    })
  )

  return Object.fromEntries(namePairs)
}
