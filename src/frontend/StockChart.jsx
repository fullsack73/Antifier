import Plot from "./LazyPlot.jsx"

function StockChart({ data, ticker, priceCurrency = "USD" }) {
  return (
    <Plot
      data={[
        {
          x: Object.keys(data),
          y: Object.values(data),
          type: "scatter",
          mode: "lines",
          line: {
            color: "#06b6d4",
            width: 2.5,
          },
          fill: "tozeroy",
          fillcolor: "rgba(6, 182, 212, 0.1)",
        },
      ]}
      layout={{
        autosize: true,
        title: {
          text: `${ticker} Stock Data`,
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
        // height: 600, // let container control height
        margin: { t: 50, b: 100, l: 50, r: 50 },
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
