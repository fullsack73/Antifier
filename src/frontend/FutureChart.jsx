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
  const chartText = "#f2f1e9"
  const chartMuted = "#a9ad9f"
  const chartGrid = "rgba(174, 186, 154, 0.1)"
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
        color: "#b3cf84",
        width: 2.25,
      },
    },
    hasForecastRange && {
      x: [...forecastDates, ...forecastDates.slice().reverse()],
      y: [...maxPrices, ...minPrices.slice().reverse()],
      type: "scatter",
      mode: "lines",
      name: t("future.forecast_range", "Forecast Range (Min-Max)"),
      fill: "toself",
      fillcolor: "rgba(198, 170, 118, 0.18)",
      line: {
        color: "rgba(198, 170, 118, 0)",
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
        color: "#c6aa76",
        width: 2.25,
      },
    },
  ].filter(Boolean)

  return (
    <Plot
      data={traces}
      layout={{
        autosize: true,
        hovermode: "x unified",
        font: { color: chartMuted, family: "Outfit, Pretendard, sans-serif" },
        hoverlabel: {
          bgcolor: "#171d18",
          bordercolor: "rgba(168, 199, 122, 0.48)",
          font: { color: chartText, size: 13, family: "Outfit, Pretendard, sans-serif" },
        },
        title: {
          text: t("future.monte_carlo_chart_title", `${ticker} Monte Carlo Future Price Forecast`),
          x: 0.02,
          xanchor: "left",
          font: { color: chartText, size: 16, family: "Outfit, Pretendard, sans-serif" },
        },
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "rgba(168, 199, 122, 0.015)",
        xaxis: {
          title: { text: t("chart.date", "Date"), font: { color: chartMuted } },
          type: "date",
          tickangle: 0,
          tickformat: "%Y-%m-%d",
          nticks: 8,
          color: chartMuted,
          gridcolor: chartGrid,
          zeroline: false,
          automargin: true,
          spikecolor: "rgba(168, 199, 122, 0.48)",
          spikethickness: 1,
          spikedash: "dot",
        },
        yaxis: {
          title: { text: t("chart.priceWithCurrency", "Price ({{currency}})", { currency: priceCurrency }), font: { color: chartMuted } },
          color: chartMuted,
          gridcolor: chartGrid,
          zeroline: false,
          automargin: true,
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
                  color: "rgba(242, 241, 233, 0.38)",
                  width: 1.5,
                  dash: "dash",
                },
              },
            ]
          : [],
        legend: {
          orientation: "h",
          x: 0,
          y: 1.06,
          font: { color: chartText },
        },
        margin: { t: 68, b: 58, l: 62, r: 24 },
      }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler={true}
      config={{
        displayModeBar: false,
        displaylogo: false,
      }}
    />
  )
}

export default FutureChart
