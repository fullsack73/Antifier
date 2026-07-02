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
        title: {
          text: t("benchmark.chartTitle"),
          font: { color: chartText, size: 18, family: "Outfit, Pretendard, sans-serif" },
        },
        paper_bgcolor: "rgba(17, 22, 17, 0.64)",
        plot_bgcolor: "rgba(8, 11, 8, 0.24)",
        xaxis: {
          title: { text: t("benchmark.date"), font: { color: chartMuted } },
          tickangle: 45,
          tickformat: "%Y-%m-%d",
          color: chartMuted,
          gridcolor: chartGrid,
        },
        yaxis: {
          title: { text: t("benchmark.portfolioValue"), font: { color: chartMuted } },
          color: chartMuted,
          gridcolor: chartGrid,
        },
        margin: { t: 50, b: 100, l: 70, r: 50 },
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

export default BenchmarkChart
