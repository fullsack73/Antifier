import { useTranslation } from "react-i18next"
import Plot from "./LazyPlot.jsx"

function BenchmarkChart({ portfolioData, sp500Data, riskfreeData }) {
  const { t } = useTranslation()
  const chartText = "#f4f1e8"
  const chartMuted = "#aeb49f"
  const chartGrid = "rgba(174, 186, 154, 0.12)"

  return (
    <Plot
      data={[
        {
          x: Object.keys(portfolioData),
          y: Object.values(portfolioData),
          type: "scatter",
          mode: "lines",
          name: t("benchmark.portfolio"),
          line: {
            color: "#a8c77a",
            width: 3,
          },
        },
        {
          x: Object.keys(sp500Data),
          y: Object.values(sp500Data),
          type: "scatter",
          mode: "lines",
          name: t("benchmark.sp500"),
          line: {
            color: "#d6a85f",
            width: 3,
          },
        },
        {
          x: Object.keys(riskfreeData),
          y: Object.values(riskfreeData),
          type: "scatter",
          mode: "lines",
          name: t("benchmark.riskFree"),
          line: {
            color: "#aeb49f",
            width: 3,
          },
        },
      ]}
      layout={{
        autosize: true,
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "rgba(0, 0, 0, 0)",
        font: {
          color: chartMuted,
          family: "Outfit, Pretendard, sans-serif",
          size: 12,
        },
        hovermode: "x unified",
        xaxis: {
          title: { text: t("benchmark.date"), font: { color: chartMuted, size: 11 } },
          tickangle: 0,
          tickformat: "%Y-%m-%d",
          color: chartMuted,
          gridcolor: chartGrid,
          zeroline: false,
          automargin: true,
        },
        yaxis: {
          title: { text: t("benchmark.portfolioValue"), font: { color: chartMuted, size: 11 } },
          color: chartMuted,
          gridcolor: chartGrid,
          zeroline: false,
          tickprefix: "$",
          automargin: true,
        },
        margin: { t: 58, b: 58, l: 72, r: 24 },
        showlegend: true,
        legend: {
          x: 0,
          y: 1.12,
          xanchor: "left",
          yanchor: "top",
          orientation: "h",
          font: { color: chartText },
          bgcolor: "rgba(0, 0, 0, 0)",
        },
        uirevision: "benchmark-series",
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

export default BenchmarkChart
