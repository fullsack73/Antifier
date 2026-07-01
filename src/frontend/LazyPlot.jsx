import { lazy, Suspense } from "react"

const Plot = lazy(() => import("react-plotly.js"))

function LazyPlot(props) {
  return (
    <Suspense fallback={null}>
      <Plot {...props} />
    </Suspense>
  )
}

export default LazyPlot
