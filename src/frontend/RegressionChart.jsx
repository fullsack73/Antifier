import Plot from "react-plotly.js"

function RegressionChart({ data, regression, ticker }) {
  return (
    <Plot
      data={[
        {
          x: Object.keys(data),
          y: Object.values(data),
          type: "scatter",
          mode: "markers",
          name: "Actual Prices",
          marker: {
            color: "#06b6d4", // cyan
            size: 8,
            opacity: 0.7,
          },
        },
        {
          x: Object.keys(regression),
          y: Object.values(regression),
          type: "scatter",
          mode: "lines",
          name: "Regression Line",
          line: {
            color: "#3b82f6", // blue
            width: 3,
          },
        },
      ]}
      layout={{
        autosize: true,
        title: {
          text: `${ticker} Price Regression`,
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
          title: { text: "Price ($)", font: { color: "#94a3b8" } },
          color: "#94a3b8",
          gridcolor: "rgba(148, 163, 184, 0.1)",
        },
        // height: 600, // let container control height
        margin: { t: 50, b: 100, l: 50, r: 50 },
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

export default RegressionChart
