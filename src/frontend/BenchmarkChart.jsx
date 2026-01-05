import { useTranslation } from "react-i18next"
import Plot from "react-plotly.js"

function BenchmarkChart({ portfolioData, sp500Data, riskfreeData }) {
  const { t } = useTranslation()

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
            color: "#06b6d4", // cyan
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
            color: "#3b82f6", // blue
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
            color: "#94a3b8", // gray
            width: 3,
          },
        },
      ]}
      layout={{
        autosize: true,
        title: {
          text: t("benchmark.chartTitle"),
          font: { color: "#e5e7eb", size: 18, family: "Inter, system-ui, sans-serif" },
        },
        paper_bgcolor: "rgba(30, 41, 59, 0.5)",
        plot_bgcolor: "rgba(15, 23, 42, 0.3)",
        xaxis: {
          title: { text: t("benchmark.date"), font: { color: "#94a3b8" } },
          tickangle: 45,
          tickformat: "%Y-%m-%d",
          color: "#94a3b8",
          gridcolor: "rgba(148, 163, 184, 0.1)",
        },
        yaxis: {
          title: { text: t("benchmark.portfolioValue"), font: { color: "#94a3b8" } },
          color: "#94a3b8",
          gridcolor: "rgba(148, 163, 184, 0.1)",
        },
        margin: { t: 50, b: 100, l: 70, r: 50 },
        showlegend: true,
        legend: {
          x: 0,
          y: 1,
          xanchor: "left",
          yanchor: "top",
          font: { color: "#e5e7eb" },
          bgcolor: "rgba(30, 41, 59, 0.8)",
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
