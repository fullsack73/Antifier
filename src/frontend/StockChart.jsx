import Plot from "./LazyPlot.jsx"

function StockChart({ data, ticker, priceCurrency = "USD" }) {
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
          mode: "lines",
          line: {
            color: "#a8c77a",
            width: 2.5,
          },
          fill: "tozeroy",
          fillcolor: "rgba(168, 199, 122, 0.12)",
        },
      ]}
      layout={{
        autosize: true,
        title: {
          text: `${ticker} Stock Data`,
          font: { color: chartText, size: 18, family: "Outfit, Pretendard, sans-serif" },
        },
        paper_bgcolor: "rgba(17, 22, 17, 0.64)",
        plot_bgcolor: "rgba(8, 11, 8, 0.24)",
        xaxis: {
          title: { text: "Date", font: { color: chartMuted } },
          tickangle: 45,
          tickformat: "%Y-%m-%d",
          color: chartMuted,
          gridcolor: chartGrid,
        },
        yaxis: {
          title: { text: `Price (${priceCurrency})`, font: { color: chartMuted } },
          color: chartMuted,
          gridcolor: chartGrid,
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
