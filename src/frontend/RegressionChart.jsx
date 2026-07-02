import Plot from "./LazyPlot.jsx"
import { useTranslation } from "react-i18next"

function RegressionChart({ data, regression, ticker, priceCurrency = "USD" }) {
  const { t } = useTranslation()
  const chartText = "#f4f1e8"
  const chartMuted = "#aeb49f"
  const chartGrid = "rgba(174, 186, 154, 0.12)"

  return (
    <Plot
      data={[
        {
          x: Object.keys(data),
          y: Object.values(data),
          type: "scatter",
          mode: "markers",
          name: t("regression.actualPrices", "Actual Prices"),
          marker: {
            color: "#d6a85f",
            size: 8,
            opacity: 0.7,
          },
        },
        {
          x: Object.keys(regression),
          y: Object.values(regression),
          type: "scatter",
          mode: "lines",
          name: t("regression.regressionLine", "Regression Line"),
          line: {
            color: "#a8c77a",
            width: 3,
          },
        },
      ]}
      layout={{
        autosize: true,
        title: {
          text: t("regression.chartTitle", "{{ticker}} Price Regression", { ticker }),
          font: { color: chartText, size: 18, family: "Outfit, Pretendard, sans-serif" },
        },
        paper_bgcolor: "rgba(17, 22, 17, 0.64)",
        plot_bgcolor: "rgba(8, 11, 8, 0.24)",
        xaxis: {
          title: { text: t("chart.date", "Date"), font: { color: chartMuted } },
          tickangle: 45,
          tickformat: "%Y-%m-%d",
          color: chartMuted,
          gridcolor: chartGrid,
        },
        yaxis: {
          title: { text: t("chart.priceWithCurrency", "Price ({{currency}})", { currency: priceCurrency }), font: { color: chartMuted } },
          color: chartMuted,
          gridcolor: chartGrid,
        },
        // height: 600, // let container control height
        margin: { t: 50, b: 100, l: 50, r: 50 },
        showlegend: true,
        legend: {
          x: 0,
          y: 1,
          xanchor: "left",
          yanchor: "top",
          font: { color: chartText },
          bgcolor: "rgba(17, 22, 17, 0.82)",
        },
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

export default RegressionChart
