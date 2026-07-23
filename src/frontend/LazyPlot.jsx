import { lazy, Suspense } from "react"
import { useTranslation } from "react-i18next"

const Plot = lazy(() => import("react-plotly.js"))

function LazyPlot(props) {
  const { t } = useTranslation()

  return (
    <Suspense
      fallback={(
        <div
          className="plot-loading-state"
          role="status"
          aria-label={t("skeleton.loadingChart", "Loading chart")}
        >
          <span className="plot-loading-line" />
          <span className="plot-loading-line plot-loading-line-short" />
        </div>
      )}
    >
      <Plot {...props} />
    </Suspense>
  )
}

export default LazyPlot
