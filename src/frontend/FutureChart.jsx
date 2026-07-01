import Plot from "./LazyPlot.jsx"
import { useTranslation } from "react-i18next"

const toSeries = (data = {}) =>
  Object.entries(data)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .map(([date, value]) => ({ date, value: Number(value) }))

const normalizeForecastData = (data = {}) =>
  Object.entries(data)
    .map(([date, value]) => {
      if (value && typeof value === "object") {
        return {
          date,
          mean: Number(value.mean),
          min: Number(value.min),
          max: Number(value.max),
        }
      }

      const numericValue = Number(value)
      return {
        date,
        mean: numericValue,
        min: numericValue,
        max: numericValue,
      }
    })
    .filter(({ mean, min, max }) => Number.isFinite(mean) && Number.isFinite(min) && Number.isFinite(max))

const FutureChart = ({ data, historicalData = {}, ticker, priceCurrency = "USD" }) => {
  const { t } = useTranslation()
  const historicalSeries = toSeries(historicalData)
  const forecastSeries = normalizeForecastData(data)
  const forecastDates = forecastSeries.map(({ date }) => date)
  const meanPrices = forecastSeries.map(({ mean }) => mean)
  const minPrices = forecastSeries.map(({ min }) => min)
  const maxPrices = forecastSeries.map(({ max }) => max)
  const hasForecastRange = forecastSeries.some(({ min, max }) => min !== max)
  const forecastStartDate = forecastDates[0]

  const traces = [
    historicalSeries.length > 0 && {
      x: historicalSeries.map(({ date }) => date),
      y: historicalSeries.map(({ value }) => value),
      type: "scatter",
      mode: "lines",
      name: t("future.historical_price", "Historical Price"),
      line: {
        color: "#3b82f6",
        width: 2.5,
      },
    },
    hasForecastRange && {
      x: [...forecastDates, ...forecastDates.slice().reverse()],
      y: [...maxPrices, ...minPrices.slice().reverse()],
      type: "scatter",
      mode: "lines",
      name: t("future.forecast_range", "Forecast Range (Min-Max)"),
      fill: "toself",
      fillcolor: "rgba(251, 146, 60, 0.22)",
      line: {
        color: "rgba(251, 146, 60, 0)",
      },
      hoverinfo: "skip",
    },
    forecastSeries.length > 0 && {
      x: forecastDates,
      y: meanPrices,
      type: "scatter",
      mode: "lines",
      name: t("future.mean_forecast", "Mean Forecast"),
      line: {
        color: "#f97316",
        width: 2.5,
      },
    },
  ].filter(Boolean)

  return (
    <Plot
      data={traces}
      layout={{
        title: {
          text: t("future.monte_carlo_chart_title", `${ticker} Monte Carlo Future Price Forecast`),
          font: { color: "#e5e7eb", size: 18, family: "Inter, system-ui, sans-serif" },
        },
        paper_bgcolor: "rgba(30, 41, 59, 0.5)",
        plot_bgcolor: "rgba(15, 23, 42, 0.3)",
        xaxis: {
          title: { text: "Date", font: { color: "#94a3b8" } },
          type: "date",
          tickangle: 45,
          tickformat: "%Y-%m-%d",
          color: "#94a3b8",
          gridcolor: "rgba(148, 163, 184, 0.1)",
        },
        yaxis: {
          title: { text: `Price (${priceCurrency})`, font: { color: "#94a3b8" } },
          color: "#94a3b8",
          gridcolor: "rgba(148, 163, 184, 0.1)",
        },
        shapes: forecastStartDate
          ? [
              {
                type: "line",
                xref: "x",
                yref: "paper",
                x0: forecastStartDate,
                x1: forecastStartDate,
                y0: 0,
                y1: 1,
                line: {
                  color: "#ef4444",
                  width: 2,
                  dash: "dash",
                },
              },
            ]
          : [],
        legend: {
          orientation: "h",
          x: 0,
          y: 1.08,
          font: { color: "#cbd5e1" },
        },
        height: 460,
        margin: { t: 50, b: 100, l: 50, r: 50 },
      }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler={true}
      config={{
        displayModeBar: true,
        displaylogo: false,
      }}
    />
  )
}

export default FutureChart
