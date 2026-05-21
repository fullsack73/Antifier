const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "")

export const apiUrl = (path, params = {}) => {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  const query = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value))
    }
  })

  const queryString = query.toString()
  const relativeUrl = `${normalizedPath}${queryString ? `?${queryString}` : ""}`

  if (!API_BASE_URL) {
    return relativeUrl
  }

  return `${API_BASE_URL}${relativeUrl}`
}
