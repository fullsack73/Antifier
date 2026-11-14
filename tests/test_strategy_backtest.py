import threading
import numpy as np
import pandas as pd
import pytest

import app
import strategy_backtest as sb
from portfolio_optimization import OptimizationCancelled


def config(**kwargs):
    return sb.validate_settings({'csv': 'ticker\nAAPL\nMSFT\nAMZN\nGOOGL\nNVDA\nMETA',
        'start_date': '2024-01-02', 'end_date': '2024-04-30', 'train_window': 126,
        **kwargs})


@pytest.mark.parametrize('changes', [
    {'csv': '"ticker'}, {'csv': 'price\n100'}, {'csv': 'ticker\n../oops'}, {'csv': 'ticker\nAAPL'},
    {'forecast_horizon': 0}, {'initial_value': float('nan')}, {'train_window': True},
    {'strategies': ['unknown']}, {'max_asset_weight': .1}, {'rebalance_frequency': 1.5},
    {'start_date': '2025-01-01'},
])
def test_bad_settings(changes):
    with pytest.raises(ValueError):
        config(**changes)


def test_csv_normalizes_deduplicates_and_estimates():
    s = config(csv='\ufeffticker,name\naapl,Apple\nMSFT,Microsoft\naapl,Apple', max_asset_weight=.5)
    assert s['tickers'] == ['AAPL', 'MSFT']
    assert s['duplicates'] == ['AAPL']
    assert s['estimated_forecasts'] == 2 * s['estimated_rebalances']


@pytest.fixture
def history(monkeypatch):
    dates = pd.bdate_range('2023-06-01', '2024-04-30')
    rng = np.random.default_rng(42)
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.0003, .012, (len(dates), 6)), axis=0)),
                          index=dates, columns=config()['tickers'])
    monkeypatch.setattr(sb, 'get_stock_data', lambda *args, **kwargs: prices.copy())
    monkeypatch.setattr(sb, '_convert_price_data_to_usd', lambda frame, *args: (frame, {}, []))
    return prices


def test_shared_engine_common_dates_costs_and_no_future_training(history, monkeypatch):
    seen = []
    def forecast(ticker, series, horizon):
        seen.append((ticker, series.index[-1], len(series), horizon))
        return ticker, {'expected_return': .05 + config()['tickers'].index(ticker)*.02, 'uncertainty': .1}
    monkeypatch.setattr(sb, '_transformer_forecast_single_ticker', forecast)
    r = sb.run_comparison(config(), lambda *args: None, threading.Event())
    assert set(r['strategies']) == set(sb.STRATEGIES)
    assert r['promotion_eligible'] is False
    calendars = [list(v['equity']) for v in r['strategies'].values()]
    assert all(d == calendars[0] for d in calendars)
    for model in r['strategies'].values():
        daily = pd.Series(model['daily_returns'])
        assert (1 + daily).prod() == pytest.approx(1 + model['summary']['net_cumulative_return'])
        assert list(model['equity'].values())[-1] == pytest.approx(model['summary']['final_value'])
        assert model['summary']['transaction_costs'] > 0
        assert min(model['drawdown'].values()) == pytest.approx(model['summary']['max_drawdown'])
    for record in r['forecast_records']:
        assert record['train_end_date'] < record['date']
    assert all(n == 126 and h == 63 for _, _, n, h in seen)


def test_future_changes_do_not_change_first_forecast_inputs(history, monkeypatch):
    monkeypatch.setattr(sb, '_transformer_forecast_single_ticker',
        lambda ticker, series, horizon: (ticker, {'expected_return': float(np.log(series.iloc[-1]/series.iloc[0])), 'uncertainty': .1}))
    s = config(strategies=['model_mpt'])
    first = sb.run_comparison(s, lambda *args: None, threading.Event())
    history.loc[history.index >= '2024-01-02'] *= 1.2
    second = sb.run_comparison(s, lambda *args: None, threading.Event())
    assert first['forecast_records'][0]['annual_log_forecasts'] == second['forecast_records'][0]['annual_log_forecasts']
    assert first['forecast_records'][0]['candidate_search']['model_mpt']['selected'] == second['forecast_records'][0]['candidate_search']['model_mpt']['selected']
    assert first['strategies']['model_mpt']['rebalance_records'][0]['weights'] == second['strategies']['model_mpt']['rebalance_records'][0]['weights']


def test_later_missing_prices_fail_instead_of_dropping_asset(history):
    history.loc['2024-02-01', 'AAPL'] = np.nan
    with pytest.raises(ValueError, match='during evaluation'):
        sb.run_comparison(config(), lambda *args: None, threading.Event())


def test_no_view_is_explicit_and_gmv_is_identical(history, monkeypatch):
    from forecast_models import no_view_prediction
    monkeypatch.setattr(sb, '_transformer_forecast_single_ticker',
        lambda ticker, series, horizon: (ticker, no_view_prediction('test failure')))
    r = sb.run_comparison(config(), lambda *args: None, threading.Event())
    assert r['forecast_records'][0]['no_view_tickers']
    assert r['strategies']['gmv']['equity'] == r['strategies']['model_mpt']['equity']
    assert r['strategies']['gmv']['equity'] == r['strategies']['gmv_model']['equity']


def test_cancel_before_fetch():
    event = threading.Event(); event.set()
    with pytest.raises(OptimizationCancelled):
        sb.run_comparison(config(), lambda *args: None, event)


def test_api_validation_does_not_start_job():
    response = app.app.test_client().post('/api/strategy-backtests', json={})
    assert response.status_code == 400
    response = app.app.test_client().post('/api/strategy-backtests/preview', json={
        'csv': 'ticker\nAAPL\nMSFT\nAMZN\nGOOGL\nNVDA',
        'start_date': '2024-01-02', 'end_date': '2024-04-30',
    })
    assert response.status_code == 200
    assert response.json['estimated_forecasts'] > 0


def test_job_persists_result_and_api_restores_it(tmp_path, monkeypatch):
    import portfolio_optimization as po
    import uuid
    monkeypatch.setattr(po, 'RESULTS_DIR', tmp_path)
    expected = {'result_type': 'strategy_backtest', 'strategies': {}, 'settings': config()}
    monkeypatch.setattr(sb, 'run_comparison', lambda *args, **kwargs: expected)
    request_id = 'backtest_' + uuid.uuid4().hex
    job, _ = app.ensure_optimization_job(request_id)
    try:
        app.background_strategy_backtest(request_id, config())
        assert job.status == 'completed'
        assert request_id not in po.list_saved_portfolios()
        app.OPTIMIZATION_JOBS.pop(request_id)
        response = app.app.test_client().get('/api/optimization-jobs/' + request_id)
        assert response.status_code == 200 and response.json['status'] == 'completed'
        assert response.json['result']['result_type'] == 'strategy_backtest'
        assert request_id in app.app.test_client().get('/api/strategy-backtest-results').json['ids']
    finally:
        app.OPTIMIZATION_JOBS.pop(request_id, None)


def test_cancellation_job_does_not_save(tmp_path, monkeypatch):
    import portfolio_optimization as po
    import uuid
    monkeypatch.setattr(po, 'RESULTS_DIR', tmp_path)
    monkeypatch.setattr(sb, 'run_comparison', lambda *args, **kwargs: (_ for _ in ()).throw(OptimizationCancelled()))
    request_id = 'backtest_' + uuid.uuid4().hex
    job, _ = app.ensure_optimization_job(request_id)
    try:
        app.background_strategy_backtest(request_id, config())
        assert job.status == 'cancelled'
        assert not list(tmp_path.glob('*.json'))
    finally:
        app.OPTIMIZATION_JOBS.pop(request_id, None)


def test_common_eligibility_uses_initial_history_only(history, monkeypatch):
    history.loc[history.index < '2024-01-02', 'NVDA'] = np.nan
    s = config(max_asset_weight=.3, strategies=['gmv'])
    r = sb.run_comparison(s, lambda *args: None, threading.Event())
    assert r['exclusions'] == {'NVDA': 'missing_or_invalid_initial_history'}
    assert 'NVDA' not in r['eligible_tickers']


def test_truncated_evaluation_range_fails(history):
    history.drop(history.index[history.index > '2024-04-01'], inplace=True)
    with pytest.raises(ValueError, match='ends before'):
        sb.run_comparison(config(strategies=['gmv']), lambda *args: None, threading.Event())


@pytest.mark.parametrize('entries', [[], [None], [{'optimization_method': 'UNKNOWN'}],
    [{'optimization_method': 'MPT', 'forecast_method': 'UNKNOWN'}],
    [{'optimization_method': 'MPT', 'forecast_method': 'TRANSFORMER'}] * 2,
])
def test_bad_comparison_configs(entries):
    with pytest.raises(ValueError):
        config(strategy_configs=entries)


def test_gmv_disables_forecasts_and_workload_counts_unique_methods():
    s = config(strategy_configs=[
        {'optimization_method': 'MIN_VARIANCE', 'forecast_method': 'TRANSFORMER'},
        {'optimization_method': 'MPT', 'forecast_method': 'TRANSFORMER'},
        {'optimization_method': 'BL', 'forecast_method': 'TRANSFORMER'},
        {'optimization_method': 'MPT', 'forecast_method': 'LIGHTWEIGHT'},
    ])
    assert s['strategy_configs'][0]['forecast_method'] == 'RISK_ONLY'
    assert s['estimated_forecasts'] == len(s['tickers']) * s['estimated_rebalances'] * 2


def test_selected_methods_share_forecasts_and_have_distinct_results(history, monkeypatch):
    calls = []
    def transformer(ticker, series, horizon):
        calls.append(('TRANSFORMER', ticker, series.index[-1]))
        return ticker, {'expected_return': .04 + list(history.columns).index(ticker)*.03, 'uncertainty': .1}
    def ensemble(ticker, series, horizon):
        calls.append(('ARIMA_TRANSFORMER', ticker, series.index[-1]))
        return ticker, {'expected_return': .2 - list(history.columns).index(ticker)*.03, 'uncertainty': .2}
    monkeypatch.setattr(sb, '_transformer_forecast_single_ticker', transformer)
    monkeypatch.setattr(sb, '_ml_forecast_single_ticker', ensemble)
    s = config(strategy_configs=[
        {'optimization_method': 'MIN_VARIANCE', 'forecast_method': 'RISK_ONLY'},
        {'optimization_method': 'MPT', 'forecast_method': 'TRANSFORMER'},
        {'optimization_method': 'BL', 'forecast_method': 'TRANSFORMER'},
        {'optimization_method': 'GMV_MODEL', 'forecast_method': 'TRANSFORMER'},
        {'optimization_method': 'MPT', 'forecast_method': 'ARIMA_TRANSFORMER'},
    ])
    result = sb.run_comparison(s, lambda *args: None, threading.Event())
    assert set(result['strategies']) == set(s['strategies'])
    assert len(calls) == 2 * len(history.columns) * len(result['forecast_records'])
    for record in result['forecast_records']:
        assert set(record['forecasts_by_method']) == {'TRANSFORMER', 'ARIMA_TRANSFORMER'}
        bl = next(value for key, value in record['strategy_diagnostics'].items() if key.startswith('bl_transformer'))
        assert bl['prior_source'] == 'equal_weight_market_proxy'
        assert bl['fallback_reason'] is None
        assert len(bl['posterior_returns']) == len(history.columns)
    assert result['settings']['strategy_configs'] == s['strategy_configs']


def test_lightweight_prediction_units():
    series = pd.Series(np.linspace(100., 120., 126))
    prediction = sb.forecast_for_method('LIGHTWEIGHT', 'AAPL', series, 21)
    period = sb.lightweight_ensemble_forecast(series.to_numpy(), horizon=21)
    assert prediction['expected_return'] == pytest.approx(np.log1p(period) * 252/21)
    assert prediction['uncertainty'] >= 0


def test_gmv_only_does_not_call_any_forecast(history, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('GMV must not train a forecast')
    monkeypatch.setattr(sb, 'forecast_for_method', forbidden)
    s = config(strategy_configs=[{'optimization_method': 'MIN_VARIANCE'}])
    result = sb.run_comparison(s, lambda *args: None, threading.Event())
    assert list(result['strategies']) == ['min_variance_risk_only_price_features']
    assert s['estimated_forecasts'] == 0


@pytest.mark.parametrize('text', [
    'Symbol\nAAPL\nMSFT', ' TICKER ,Name\nAAPL,Apple\nMSFT,Microsoft',
    '\ufeffsymbol;name\r\nAAPL;Apple\r\nMSFT;Microsoft',
    'AAPL\nMSFT', 'AAPL,MSFT', 'Symbol\tName\nAAPL\tApple\nMSFT\tMicrosoft',
    '종목코드,기업명\nAAPL,Apple\nMSFT,Microsoft',
])
def test_common_ticker_csv_formats(text):
    assert sb.parse_ticker_csv(text)['tickers'] == ['AAPL', 'MSFT']


def test_repository_sp500_and_dow_csv_are_accepted():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ['snp.csv', 'dow.csv', 'nyse.csv']:
        data = sb.parse_ticker_csv((root/name).read_text())
        assert len(data['tickers']) >= 29
        assert data['tickers'][0] != 'SYMBOL'


def test_universe_inspection_is_independent_of_dates_and_models():
    response = app.app.test_client().post('/api/strategy-backtests/universe', json={'csv':'Symbol\nAAPL\nMSFT\nAAPL'})
    assert response.status_code == 200
    assert response.json == {'tickers':['AAPL','MSFT'],'duplicates':['AAPL']}


def test_checkpoint_resume_reuses_committed_predictions(history, monkeypatch):
    from strategy_job_checkpoint import save, load
    import uuid
    calls=[]
    monkeypatch.setattr(sb,'_transformer_forecast_single_ticker',
        lambda ticker,series,horizon:(calls.append(ticker) or ticker,{'expected_return':.05,'uncertainty':.1}))
    settings=config(strategies=['model_mpt'])
    request_id='backtest_'+uuid.uuid4().hex
    first=sb.run_comparison(settings,lambda *a:None,threading.Event(),checkpoint=lambda s:save(request_id,s))
    count=len(calls)
    again=sb.run_comparison(load(request_id),lambda *a:None,threading.Event())
    assert len(calls)==count
    assert again['strategies']['model_mpt']['equity']==first['strategies']['model_mpt']['equity']
    assert all(d['replayed'] for d in again['strategies']['model_mpt']['candidate_decisions'])


def test_manager_async_uses_existing_job_protocol(monkeypatch):
    import uuid
    result={'weights':{'AAPL':1},'prices':{'AAPL':100}}
    monkeypatch.setattr(app,'manage_portfolio_logic',lambda **kwargs:dict(result))
    monkeypatch.setattr('portfolio_optimization.save_portfolio_result',lambda *a:None)
    request_id='manage_'+uuid.uuid4().hex
    try:
        response=app.app.test_client().post('/api/manage-portfolio',json={
            'async':True,'request_id':request_id,'current_holdings':{'AAPL':1},
            'start_date':'2024-01-01','end_date':'2024-04-30'})
        assert response.status_code==202
        app.OPTIMIZATION_JOBS[request_id].thread.join(timeout=5)
        status=app.app.test_client().get('/api/optimization-jobs/'+request_id).json
        assert status['status']=='completed' and status['result']==result
    finally:app.OPTIMIZATION_JOBS.pop(request_id,None)


@pytest.mark.parametrize('mode,enabled', [('forecast_profile',True),('price_features',True),('frozen_forecast',True),('forecast_profile',False)])
def test_workload_separates_initial_full_and_partial_forecasts(mode, enabled):
    s=config(csv='ticker\n'+'\n'.join(f'T{i:03}' for i in range(513)),rebalance_frequency=8,
        strategy_configs=[{'optimization_method':'MPT','forecast_method':'TRANSFORMER',
            'candidate_search':{'mode':mode,'enabled':enabled,'refresh_interval':16}}])
    row=s['forecast_workloads'][0]; steps=s['estimated_rebalances']
    full=steps if not enabled else 1+(steps-1)//2 if mode=='forecast_profile' else 1
    assert row['initial_forecasts_upper_bound']==513
    assert row['full_rebalances']==full and row['partial_rebalances']==steps-full
    assert row['total_before_cache']==(None if enabled else 513*steps)
    assert row['total_upper_bound']==513*steps
    assert s['initial_forecasts_upper_bound']==513


def test_workload_gmv_has_zero_forecasts_and_shared_methods_are_not_added():
    s=config(strategy_configs=[{'optimization_method':'MIN_VARIANCE'},
        *[{'optimization_method':'MPT','forecast_method':'TRANSFORMER','candidate_search':{'mode':mode}}
          for mode in ['forecast_profile','price_features','frozen_forecast']]])
    row=s['forecast_workloads'][0]
    assert row['total_before_cache']==row['initial_forecasts_upper_bound']==row['total_upper_bound']==0
    assert s['estimated_forecasts']==len(s['tickers'])*s['estimated_rebalances']
    assert s['initial_forecasts_upper_bound']==len(s['tickers'])
