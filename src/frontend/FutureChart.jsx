import Plot from "react-plotly.js"
import { useTranslation } from "react-i18next"

const FutureChart = ({ data, ticker, priceCurrency = "USD" }) => {
  const { t } = useTranslation()

  return (
    <Plot
      data={[
        {
          x: Object.keys(data),
          y: Object.values(data),
          type: "scatter",
          mode: "lines",
          name: t("future.predicted_price", "Predicted Price"),
          line: {
            color: "#10b981", // emerald green
            width: 2.5,
            dash: "dot",
          },
          fill: "tozeroy",
          fillcolor: "rgba(16, 185, 129, 0.1)",
        },
      ]}
      layout={{
        title: {
          text: t("future.chart_title", `${ticker} Future Price Prediction`),
          font: { color: "#e5e7eb", size: 18, family: "Inter, system-ui, sans-serif" },
        },
        paper_bgcolor: "rgba(30, 41, 59, 0.5)",
        plot_bgcolor: "rgba(15, 23, 42, 0.3)",
        xaxis: {
          title: { text: "Date", font: { color: "#94a3b8" } },
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
        height: 400,
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
