import Plot from "./LazyPlot.jsx"
import { useTranslation } from "react-i18next"
import { getPriceAxisLayout, PRICE_NUMBER_FORMAT } from "./priceChartAxis.js"

function StockChart({ data, ticker, priceCurrency = "USD" }) {
  const { t } = useTranslation()
  const chartText = "#f2f1e9"
  const chartMuted = "#a9ad9f"
  const chartGrid = "rgba(174, 186, 154, 0.1)"
  const prices = Object.values(data)

  return (
    <Plot
      data={[
        {
          x: Object.keys(data),
          y: prices,
          type: "scatter",
          mode: "lines",
          line: {
            color: "#b3cf84",
            width: 2.25,
          },
          hovertemplate: `%{x}<br>%{y:${PRICE_NUMBER_FORMAT}} ${priceCurrency}<extra></extra>`,
        },
      ]}
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
          text: t("stock.chartTitle", "{{ticker}} Stock Data", { ticker }),
          x: 0.02,
          xanchor: "left",
          font: { color: chartText, size: 16, family: "Outfit, Pretendard, sans-serif" },
        },
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "rgba(168, 199, 122, 0.015)",
        xaxis: {
          title: { text: t("chart.date", "Date"), font: { color: chartMuted } },
          tickangle: 0,
          tickformat: "%Y-%m-%d",
          nticks: 6,
          color: chartMuted,
          gridcolor: chartGrid,
          zeroline: false,
          automargin: true,
          spikecolor: "rgba(168, 199, 122, 0.48)",
          spikethickness: 1,
          spikedash: "dot",
        },
        yaxis: {
          ...getPriceAxisLayout(prices),
          title: { text: t("chart.priceWithCurrency", "Price ({{currency}})", { currency: priceCurrency }), font: { color: chartMuted } },
          color: chartMuted,
          gridcolor: chartGrid,
          zeroline: false,
          automargin: true,
        },
        margin: { t: 48, b: 58, l: 62, r: 24 },
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

export default StockChart
