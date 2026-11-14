import { act, fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"
import { afterEach, describe, expect, it, vi } from "vitest"
import StrategyBacktest from "../src/frontend/StrategyBacktest.jsx"

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: key => key }) }))
vi.mock("../src/frontend/LazyPlot.jsx", () => ({ default: () => <div>Chart</div> }))
vi.mock("../src/frontend/DateInput.jsx", () => ({ default: ({ onDateRangeChange }) =>
  <button type="button" onClick={() => onDateRangeChange("2024-01-01", "2025-01-01")}>Dates</button> }))
const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data })
afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals() })

describe("Strategy comparison", () => {
  it("validates CSV and common settings before starting a job", async () => {
    const calls = []
    vi.stubGlobal("fetch", vi.fn(async (url, options) => {
      calls.push([url, options])
      if (url.includes("/universe")) return reply({ tickers: ["AAPL", "MSFT"], duplicates: [] })
      if (url.includes("preview")) return reply({ tickers: ["AAPL", "MSFT"], duplicates: [], estimated_rebalances: 4, estimated_forecasts: 8 })
      if (url.endsWith("/api/strategy-backtests")) return reply({ request_id: "backtest_test" }, 202)
      if (url.includes("optimization-jobs")) return reply({ status: "running", progress: 20, message: "Working" })
      return reply({ ids: [] })
    }))
    render(<StrategyBacktest />)
    const input = document.querySelector('input[type="file"]')
    await act(async () => fireEvent.change(input, { target: { files: [{ name: "symbols.csv", size: 24, text: async () => "ticker\nAAPL\nMSFT" }] } }))
    fireEvent.click(screen.getByText("Dates"))
    fireEvent.change(screen.getByLabelText("strategyBacktest.max_asset_weight"), { target: { value: "50" } })
    expect(screen.getByLabelText("optimizer.forecastMethod")).toBeDisabled()
    fireEvent.click(screen.getByText("strategyBacktest.addStrategy"))
    fireEvent.change(screen.getAllByLabelText("optimizer.optimizationMethod")[1], { target: { value: "BL" } })
    fireEvent.change(screen.getAllByLabelText("optimizer.forecastMethod")[1], { target: { value: "ARIMA_TRANSFORMER" } })
    fireEvent.click(screen.getByText("strategyBacktest.preview"))
    await screen.findByText("strategyBacktest.run")
    expect(calls.some(([url]) => url.endsWith("/api/strategy-backtests"))).toBe(false)
    fireEvent.click(screen.getByText("strategyBacktest.run"))
    await screen.findByText("Working")
    const payload = JSON.parse(calls.find(([url]) => url.endsWith("/api/strategy-backtests"))[1].body)
    expect(payload.max_asset_weight).toBe(.5)
    expect(payload.max_turnover).toBe(.35)
    expect(payload.csv).toContain("MSFT")
    expect(payload.strategy_configs.map(({ optimization_method, forecast_method }) => ({ optimization_method, forecast_method }))).toEqual([
      { optimization_method: "MIN_VARIANCE", forecast_method: "RISK_ONLY" },
      { optimization_method: "BL", forecast_method: "ARIMA_TRANSFORMER" },
    ])
    expect(payload.strategies).toBeUndefined()
    expect(localStorage.getItem("antifier.strategyBacktest.job")).toBe("backtest_test")
  })

  it("reconnects to a stored job and requests cancellation", async () => {
    localStorage.setItem("antifier.strategyBacktest.job", "backtest_resume")
    const fetch = vi.fn(async url => url.includes("strategy-backtest-results") ? reply({ ids: [] })
      : reply({ status: "running", progress: 40, message: "Resumed" }))
    vi.stubGlobal("fetch", fetch)
    render(<StrategyBacktest />)
    await screen.findByText("Resumed")
    fireEvent.click(screen.getByText("strategyBacktest.cancel"))
    await waitFor(() => expect(fetch.mock.calls.some(([url, options]) =>
      url.endsWith("/backtest_resume/cancel") && options.method === "POST")).toBe(true))
  })

  it("rejects oversized files without reading or submitting them", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ ids: [] })))
    render(<StrategyBacktest />)
    const text = vi.fn()
    fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [{ size: 1000001, text }] } })
    expect(await screen.findByRole("alert")).toHaveTextContent("strategyBacktest.fileTooLarge")
    expect(text).not.toHaveBeenCalled()
  })
})

it("labels saved results with the recorded optimizer and forecast combination", async () => {
  localStorage.setItem("antifier.strategyBacktest.job", "backtest_labels")
  const record = { rebalance_date: "2024-01-02", period_end_date: "2024-04-01", controlled_weights: { AAPL: 1 }, net_period_return: .01 }
  const result = {
    settings: { strategy_configs: [
      { id: "mpt_lightweight", optimization_method: "MPT", forecast_method: "LIGHTWEIGHT" },
      { id: "mpt_transformer", optimization_method: "MPT", forecast_method: "TRANSFORMER" },
    ] }, eligible_tickers: ["AAPL"], exclusions: {},
    strategies: Object.fromEntries(["mpt_lightweight", "mpt_transformer"].map(id => [id,
      { summary: {}, equity: {}, drawdown: {}, rebalance_records: [record] }])),
    forecast_records: [{ date: "2024-01-02", train_end_date: "2024-01-01", forecasts_by_method: {
      LIGHTWEIGHT: { annual_log_forecasts: { AAPL: .1 }, no_view_tickers: [] },
      TRANSFORMER: { annual_log_forecasts: { AAPL: .2 }, no_view_tickers: [] },
    }, strategy_diagnostics: {} }],
  }
  vi.stubGlobal("fetch", vi.fn(async url => url.includes("strategy-backtest-results") ? reply({ ids: [] })
    : reply({ status: "completed", result })))
  render(<StrategyBacktest />)
  await screen.findByRole("rowheader", { name: "optimizer.mpt · optimizer.lightweight" })
  expect(screen.getByRole("rowheader", { name: "optimizer.mpt · optimizer.transformer" })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("strategyBacktest.rebalanceDetail"), { target: { value: "2024-01-02" } })
  expect(screen.getByRole("cell", { name: "10.00%" })).toBeInTheDocument()
  expect(screen.getByRole("cell", { name: "20.00%" })).toBeInTheDocument()
})

it("decodes Excel UTF-16 CSV before inspecting its symbols", async () => {
  const csv = 'Symbol\r\nAAPL\r\nMSFT'
  const bytes = new Uint8Array([255, 254, ...Array.from(csv).flatMap(c => [c.charCodeAt(0), 0])])
  const fetch = vi.fn(async url => url.includes('/universe')
    ? reply({ tickers: ['AAPL', 'MSFT'], duplicates: [] }) : reply({ ids: [] }))
  vi.stubGlobal('fetch', fetch)
  render(<StrategyBacktest />)
  await act(async () => fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [
    { name: 'excel.csv', size: bytes.length, arrayBuffer: async () => bytes.buffer },
  ] } }))
  await screen.findByText('excel.csv')
  const request = fetch.mock.calls.find(([url]) => url.endsWith('/universe'))
  expect(JSON.parse(request[1].body).csv).toBe(csv)
  expect(screen.getByText('strategyBacktest.recognized')).toBeInTheDocument()
})

it("explains an outdated backend rather than claiming the CSV is unreadable", async () => {
  vi.stubGlobal('fetch', vi.fn(async url => url.includes('/universe')
    ? { ok: false, status: 404, json: async () => { throw new Error('HTML response') } } : reply({ ids: [] })))
  render(<StrategyBacktest />)
  await act(async () => fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [
    { name: 'symbols.csv', size: 24, text: async () => 'Symbol\nAAPL\nMSFT' },
  ] } }))
  expect(await screen.findByRole('alert')).toHaveTextContent('strategyBacktest.restartBackend')
})

it('shows frozen-map workload as initial plus dynamic partial forecasts, with GMV at zero', async () => {
  const tickers=Array.from({length:513},(_,i)=>`T${i}`)
  vi.stubGlobal('fetch',vi.fn(async url=>{
    if(url.includes('/universe')) return reply({tickers,duplicates:[]})
    if(url.includes('/preview')) return reply({tickers,duplicates:[],estimated_rebalances:11,estimated_forecasts:5643,initial_forecasts_upper_bound:513,
      forecast_workloads:[
        {id:'gmv',optimization_method:'MIN_VARIANCE',forecast_method:'RISK_ONLY',mode:'full',total_before_cache:0},
        {id:'frozen',optimization_method:'MPT',forecast_method:'TRANSFORMER',mode:'frozen_forecast',
          initial_forecasts_upper_bound:513,full_rebalances:1,partial_rebalances:10,similar_count:10,explore_count:10},
      ]})
    return reply({ids:[]})
  }))
  render(<StrategyBacktest />)
  await act(async()=>fireEvent.change(document.querySelector('input[type="file"]'),{target:{files:[
    {name:'symbols.csv',size:3000,text:async()=>`ticker\n${tickers.join('\n')}`},
  ]}}))
  fireEvent.click(screen.getByText('Dates'))
  fireEvent.click(screen.getByText('strategyBacktest.preview'))
  await screen.findByText('strategyBacktest.run')
  expect(screen.getByText('strategyBacktest.forecastUpperBound: 5643')).toBeInTheDocument()
  expect(screen.getByText('strategyBacktest.initialForecasts: 513')).toBeInTheDocument()
  expect(screen.getByText(/strategyBacktest.fullForecastSteps: 1/)).toHaveTextContent('strategyBacktest.partialForecastSteps: 10')
  expect(screen.getByText('strategyBacktest.sharedInitialForecasts: 513')).toBeInTheDocument()
  expect(screen.getByText('strategyBacktest.forecastTotalUnknown')).toBeInTheDocument()
  expect(screen.getByText('strategyBacktest.frozenWorkload')).toBeInTheDocument()
  expect(screen.getByText('strategyBacktest.noModelForecasts')).toBeInTheDocument()
  expect(screen.queryByText('strategyBacktest.fullForecastTotal: 5643')).not.toBeInTheDocument()
})

it('offers resume for backend error status and clears the old failure after retry',async()=>{
  localStorage.setItem('antifier.strategyBacktest.job','backtest_offline')
  let resumed=false
  vi.stubGlobal('fetch',vi.fn(async url=>{
    if(url.includes('strategy-backtest-results')) return reply({ids:[]})
    if(url.endsWith('/resume')) {resumed=true;return reply({status:'running'},202)}
    return reply(resumed ? {status:'running',message:'Recovered'} : {status:'error',error:'No price history available'})
  }))
  render(<StrategyBacktest />)
  expect(await screen.findByRole('alert')).toHaveTextContent('No price history available')
  fireEvent.click(screen.getByText('candidateSearch.resume'))
  await screen.findByText('Recovered')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
