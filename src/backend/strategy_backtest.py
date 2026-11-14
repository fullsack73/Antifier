"""User-configured, fixed-universe walk-forward comparisons on the shared engine."""
import csv
import io
import json
import math
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, BlackLittermanModel, black_litterman

from portfolio_optimization import (
    _raise_if_cancelled, get_stock_data,
    _convert_price_data_to_usd, _transformer_forecast_single_ticker,
    _is_no_view_prediction, _annual_log_return_to_simple_return, _ml_forecast_single_ticker,
    _confidence_from_uncertainty, _shrink_expected_returns,
    MIN_FORECAST_CONFIDENCE, MAX_FORECAST_UNCERTAINTY,
)
from portfolio_backtest import (
    _safe_covariance, _efficient_frontier_weights, _rebalance_target_signature,
    run_portfolio_model_backtest,
)
from portfolio_signals import confidence_gated_gmv_overlay
from ticker_symbols import normalize_yahoo_ticker
from lightweight_forecast import lightweight_ensemble_forecast
from candidate_search import CandidateStore, normalize_policy

STRATEGIES = ('gmv', 'model_mpt', 'gmv_model')

FORECAST_METHODS = ('LIGHTWEIGHT', 'ARIMA_TRANSFORMER', 'TRANSFORMER')
OPTIMIZATION_METHODS = ('MIN_VARIANCE', 'MPT', 'BL', 'GMV_MODEL')
LEGACY_CONFIGS = {
    'gmv': {'id': 'gmv', 'optimization_method': 'MIN_VARIANCE', 'forecast_method': 'RISK_ONLY'},
    'model_mpt': {'id': 'model_mpt', 'optimization_method': 'MPT', 'forecast_method': 'TRANSFORMER'},
    'gmv_model': {'id': 'gmv_model', 'optimization_method': 'GMV_MODEL', 'forecast_method': 'TRANSFORMER'},
}


def normalize_strategies(payload):
    if 'strategy_configs' not in payload:
        names = payload.get('strategies', list(STRATEGIES))
        if not isinstance(names, list) or not names or any(not isinstance(n, str) or n not in LEGACY_CONFIGS for n in names):
            raise ValueError('Select supported strategies')
        return [dict(LEGACY_CONFIGS[n], candidate_search=normalize_policy(payload.get('candidate_search'))) for n in dict.fromkeys(names)]
    entries = payload['strategy_configs']
    if not isinstance(entries, list) or not 1 <= len(entries) <= 10:
        raise ValueError('Select 1–10 distinct strategy combinations')
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Each strategy must specify optimization and forecast methods')
        method, forecast = entry.get('optimization_method'), entry.get('forecast_method')
        if method not in OPTIMIZATION_METHODS:
            raise ValueError('Unsupported optimization method')
        if method == 'MIN_VARIANCE':
            forecast = 'RISK_ONLY'
        elif forecast not in FORECAST_METHODS:
            raise ValueError('Unsupported forecast method')
        key = method.lower() + '_' + forecast.lower()
        policy = normalize_policy(entry.get('candidate_search', payload.get('candidate_search')))
        if method == 'MIN_VARIANCE':
            policy['mode'] = 'price_features'
        key += '_' + (policy['mode'] if policy['enabled'] else 'full')
        if key in {c['id'] for c in result}:
            raise ValueError('Duplicate strategy combination')
        result.append({'id': key, 'optimization_method': method, 'forecast_method': forecast, 'candidate_search': policy,
                       'campaign_id': entry.get('campaign_id')})
    return result


def forecast_for_method(method, ticker, series, horizon):
    if method == 'TRANSFORMER':
        return _transformer_forecast_single_ticker(ticker, series, horizon=horizon)[1]
    if method == 'ARIMA_TRANSFORMER':
        return _ml_forecast_single_ticker(ticker, series, horizon=horizon)[1]
    period_return = float(lightweight_ensemble_forecast(series.to_numpy(), horizon=horizon))
    if not np.isfinite(period_return) or period_return <= -1:
        return {'expected_return': None, 'source': 'no_view'}
    return {'expected_return': float(np.log1p(period_return) * 252 / horizon),
            'uncertainty': float(np.log(series).diff().std() * np.sqrt(252)),
            'source': 'lightweight'}


def allocate_strategy(config, forecasts, covariance, gmv, settings):
    method = config['optimization_method']
    diagnostic = {'fallback_reason': None, 'prior_source': None}
    if method == 'MIN_VARIANCE':
        return dict(gmv), diagnostic
    missing = forecasts['no_view_tickers']
    if missing:
        diagnostic['fallback_reason'] = 'no_view: ' + ', '.join(missing)
        return dict(gmv), diagnostic
    raw = pd.Series(forecasts['annual_log_forecasts'], dtype=float).reindex(covariance.index)
    if method == 'GMV_MODEL':
        weights, _ = confidence_gated_gmv_overlay(gmv, raw, {'active': True, 'strength': 1.},
            max_asset_weight=settings['max_asset_weight'], target_active_share=.025)
        return weights.to_dict(), diagnostic
    try:
        mu = raw.map(_annual_log_return_to_simple_return)
        allocation_covariance = covariance
        if method == 'BL':
            diagnostic.update(prior_source='equal_weight_market_proxy', risk_aversion=2.5, tau=.05)
            prior = black_litterman.market_implied_prior_returns(
                {ticker: 1. for ticker in covariance.index}, 2.5, covariance,
                risk_free_rate=settings['risk_free_rate'])
            uncertainty = pd.Series(forecasts['uncertainties'], dtype=float).reindex(mu.index)
            confidence = _confidence_from_uncertainty(uncertainty)
            adjusted = _shrink_expected_returns(mu, prior, confidence)
            effective = (uncertainty / confidence.clip(lower=MIN_FORECAST_CONFIDENCE)).clip(
                lower=1e-4, upper=MAX_FORECAST_UNCERTAINTY)
            bl = BlackLittermanModel(covariance, pi=prior, absolute_views=adjusted,
                omega=np.diag(effective ** 2), risk_aversion=2.5, tau=.05)
            mu, allocation_covariance = bl.bl_returns(), bl.bl_cov()
            diagnostic['posterior_returns'] = mu.to_dict()
        frontier = EfficientFrontier(mu, allocation_covariance,
                                    weight_bounds=(0, settings['max_asset_weight']))
        frontier.max_sharpe(risk_free_rate=settings['risk_free_rate'])
        return dict(frontier.clean_weights()), diagnostic
    except Exception as exc:
        diagnostic['fallback_reason'] = method.lower() + '_solver: ' + str(exc)
        return dict(gmv), diagnostic


MAX_TICKERS = 2000


def parse_ticker_csv(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 1_000_000:
        raise ValueError('CSV must be text smaller than 1 MB')
    text = text.lstrip('\ufeff').strip()
    try:
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect, strict=True)
                if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise ValueError('Invalid CSV: ' + str(exc)) from exc
    if not rows:
        raise ValueError('CSV contains no ticker symbols')
    headers = [cell.lstrip('\ufeff').lower() for cell in rows[0]]
    columns = [i for i, value in enumerate(headers) if value in {'ticker', 'symbol', '티커', '종목코드'}]
    if len(columns) > 1:
        raise ValueError('CSV must contain only one ticker or Symbol column')
    if columns:
        index = columns[0]
        values = [row[index] if index < len(row) else '' for row in rows[1:]]
    else:
        if any(value in {'price', 'close', 'open', 'volume', 'date', 'timestamp', 'name', 'company'} for value in headers):
            raise ValueError('Use a ticker/Symbol column or a list of ticker symbols')
        values = [value for row in rows for value in row if value]
    tickers, duplicates = [], []
    for value in values:
        ticker = value.upper()
        if not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=\-]{0,31}', ticker):
            raise ValueError('CSV contains an invalid ticker: ' + value[:40])
        ticker = normalize_yahoo_ticker(ticker)
        if ticker in tickers:
            duplicates.append(ticker)
        else:
            tickers.append(ticker)
    if not 2 <= len(tickers) <= MAX_TICKERS:
        raise ValueError(f'Provide 2–{MAX_TICKERS:,} distinct tickers (received {len(tickers):,})')
    return {'tickers': tickers, 'duplicates': sorted(set(duplicates))}


def validate_settings(payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected a JSON object')
    settings = parse_ticker_csv(payload.get('csv', ''))
    tickers = settings['tickers']
    for key in ('start_date', 'end_date'):
        value = payload.get(key)
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Dates must use YYYY-MM-DD')
        datetime.strptime(value, '%Y-%m-%d')
        settings[key] = value
    if settings['start_date'] >= settings['end_date'] or settings['end_date'] > datetime.now().date().isoformat():
        raise ValueError('Use a past date range with start before end')
    fields = {
        'train_window': (504, 126, 2520, True),
        'rebalance_frequency': (63, 1, 2520, True),
        'forecast_horizon': (63, 1, 252, True),
        'initial_value': (10000, 1, 1e12, False),
        'max_asset_weight': (.2, .01, 1, False),
        'transaction_cost_bps': (10, 0, 1000, False),
        'rebalance_band': (.02, 0, 1, False),
        'max_turnover': (.35, .001, 2, False),
        'risk_free_rate': (.02, 0, 1, False),
    }
    for key, (default, low, high, integer) in fields.items():
        value = payload.get(key, default)
        if isinstance(value, bool):
            raise ValueError(f'Invalid {key}')
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f'Invalid {key}') from None
        if not math.isfinite(value) or not low <= value <= high or (integer and value != int(value)):
            raise ValueError(f'Invalid {key}: expected {low}–{high}')
        settings[key] = int(value) if integer else value
    configs = normalize_strategies(payload)
    settings['strategy_configs'] = configs
    settings['strategies'] = [c['id'] for c in configs]
    if len(tickers) * settings['max_asset_weight'] < 1 - 1e-9:
        raise ValueError('Too few tickers for the maximum asset weight')
    days = int(np.busday_count(settings['start_date'], settings['end_date']))
    settings['estimated_rebalances'] = max(1, math.ceil(days / settings['rebalance_frequency']))
    settings['estimated_forecasts'] = (len(tickers) * settings['estimated_rebalances']
                                       * len({c['forecast_method'] for c in configs if c['forecast_method'] != 'RISK_ONLY'}))
    settings['initial_forecasts_upper_bound'] = len(tickers) * len({
        c['forecast_method'] for c in configs if c['forecast_method'] != 'RISK_ONLY'})
    workloads = []
    for config in configs:
        policy = config['candidate_search']
        risk_only = config['forecast_method'] == 'RISK_ONLY'
        mode = ('price_features' if risk_only else policy['mode']) if policy['enabled'] else 'full'
        rebalances = settings['estimated_rebalances']
        if mode == 'full':
            full = rebalances
        elif mode == 'forecast_profile':
            refresh_steps = math.ceil(policy['refresh_interval'] / settings['rebalance_frequency'])
            full = 1 + (rebalances - 1) // refresh_steps
        else:
            full = 1
        workloads.append(dict(id=config['id'], optimization_method=config['optimization_method'],
            forecast_method=config['forecast_method'], mode=mode,
            initial_forecasts_upper_bound=0 if risk_only else len(tickers),
            full_rebalances=0 if risk_only else full,
            partial_rebalances=0 if risk_only else rebalances - full,
            similar_count=policy['similar_count'], explore_count=policy['explore_count'],
            refresh_interval=policy['refresh_interval'],
            total_before_cache=(0 if risk_only else len(tickers) * rebalances) if risk_only or mode == 'full' else None,
            total_upper_bound=0 if risk_only else len(tickers) * rebalances))
    settings['forecast_workloads'] = workloads
    if settings['estimated_forecasts'] > 50000:
        raise ValueError('More than 50,000 forecasts; increase rebalance interval or shorten dates')
    return settings


def _create_forecast_pool():
    import multiprocessing as mp
    from portfolio_optimization import worker_initializer
    return mp.get_context('spawn').Pool(processes=1, initializer=worker_initializer, maxtasksperchild=10)


def run_comparison(settings, progress, cancel_event, checkpoint=None):
    import multiprocessing as mp
    pool = None
    def forecast(method, ticker, series, horizon):
        nonlocal pool
        _raise_if_cancelled(cancel_event)
        if method not in {'TRANSFORMER', 'ARIMA_TRANSFORMER'}:
            return forecast_for_method(method, ticker, series, horizon)
        if pool is None:
            pool = _create_forecast_pool()
        pending = pool.apply_async(forecast_for_method, (method, ticker, series, horizon))
        while True:
            _raise_if_cancelled(cancel_event)
            try:
                return pending.get(timeout=.25)
            except mp.TimeoutError:
                continue
    try:
        return _run_comparison(settings, progress, cancel_event, checkpoint, forecast)
    finally:
        if pool is not None:
            pool.terminate()
            pool.join()


def _run_comparison(settings, progress, cancel_event, checkpoint, forecast):
    s = settings
    check = lambda: _raise_if_cancelled(cancel_event)
    check()
    start = pd.Timestamp(s['start_date'])
    download_start = (start - timedelta(days=s['train_window'] * 2 + 60)).date().isoformat()
    # Yahoo end is exclusive; user-selected end is inclusive.
    download_end = (pd.Timestamp(s['end_date']) + timedelta(days=1)).date().isoformat()
    progress(0, 100, 'Downloading shared price history')
    prices = get_stock_data(s['tickers'], download_start, download_end, cancel_event=cancel_event, preserve_missing=True)
    if prices.empty:
        raise ValueError('No price history available')
    prices, _, failures = _convert_price_data_to_usd(prices, download_start, download_end)
    if failures:
        raise ValueError('USD conversion unavailable: ' + ', '.join(failures))
    prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
    prices = prices.sort_index().loc[:s['end_date']].replace([np.inf, -np.inf], np.nan)
    if prices.index.has_duplicates:
        raise ValueError('Duplicate trading dates')
    if prices.empty or (pd.Timestamp(s['end_date']) - prices.index[-1]).days > 7:
        raise ValueError('Price history ends before the requested evaluation range')
    first = prices.index.searchsorted(start)
    if first < s['train_window'] or first >= len(prices) - 1:
        raise ValueError('Insufficient warm-up history or evaluation trading days')
    if (prices.index[first] - start).days > 7:
        raise ValueError('Price history starts after the requested evaluation range')
    initial = prices.iloc[first-s['train_window']:first+1]
    eligible, exclusions = [], {}
    for ticker in s['tickers']:
        if ticker not in initial or initial[ticker].isna().any() or (initial[ticker] <= 0).any():
            exclusions[ticker] = 'missing_or_invalid_initial_history'
        else:
            eligible.append(ticker)
    if len(eligible) < 2 or len(eligible) * s['max_asset_weight'] < 1 - 1e-9:
        raise ValueError('Insufficient eligible tickers for the weight cap: ' + ', '.join(exclusions))
    prices = prices.iloc[first-s['train_window']:].reindex(columns=eligible)
    # Do not select winners by dropping assets with later missing data or silently carry stale prices.
    if prices.isna().any().any() or (prices <= 0).any().any():
        raise ValueError('Missing/invalid prices during evaluation; refusing a retrospectively filtered universe')
    origins = list(range(s['train_window'], len(prices)-1, s['rebalance_frequency']))
    forecast_records = []
    result = {'result_type': 'strategy_backtest', 'settings': s, 'eligible_tickers': eligible,
              'exclusions': exclusions, 'universe_policy': 'fixed_csv_initial_history_eligibility',
              'experimental_strategies': [c['id'] for c in s['strategy_configs'] if c['optimization_method'] == 'GMV_MODEL'], 'overlay_active_share': .025,
              'forecast_records': forecast_records, 'strategies': {}, 'promotion_eligible': False,
              'effective_start_date': str(prices.index[s['train_window']].date()),
              'effective_end_date': str(prices.index[-1].date())}
    signature = _rebalance_target_signature(prices, ['min_variance'], s['train_window'],
        s['rebalance_frequency'], s['forecast_horizon'], s['max_asset_weight'], 0., None,
        s['risk_free_rate'], None, None, None)
    store = CandidateStore()
    for number, config in enumerate(s['strategy_configs']):
        name = config['id']
        method = config['forecast_method']
        campaign = config.get('campaign_id')
        pending = {}
        decisions = []
        def provide(train, date, states):
            nonlocal campaign
            check()
            held = states['min_variance']['shares'].to_dict()
            decision = store.prepare(train, held, config['candidate_search'], method=method,
                horizon=s['forecast_horizon'], train_window=s['train_window'],
                forecast=lambda ticker, series, horizon: forecast(method, ticker, series, horizon),
                campaign_id=campaign, cancel_event=cancel_event,
                progress=lambda event: progress(5 + 90 * (number + len(decisions)/len(origins))/len(s['strategies']),
                    100, f'{date}: {method} ' + json.dumps(event)))
            campaign = decision.campaign_id
            selected = decision.report['selected']
            if len(selected) * s['max_asset_weight'] < 1-1e-9:
                raise ValueError('Candidate set cannot satisfy the maximum asset weight; increase candidate budgets')
            subset = train[selected]
            covariance = _safe_covariance(subset)
            gmv = _efficient_frontier_weights(pd.Series(0., index=selected), covariance,
                s['max_asset_weight'], 'min_volatility', s['risk_free_rate'])
            raw, uncertainties, missing = {}, {}, []
            for ticker, prediction in decision.predictions.items():
                if _is_no_view_prediction(prediction):
                    missing.append(ticker)
                else:
                    raw[ticker] = prediction['expected_return']
                    value = prediction.get('uncertainty')
                    uncertainties[ticker] = value if value is not None else MAX_FORECAST_UNCERTAINTY
            forecasts = {'annual_log_forecasts': raw, 'uncertainties': uncertainties, 'no_view_tickers': missing}
            weights, diagnostic = allocate_strategy(config, forecasts, covariance, gmv, s)
            record = next((r for r in forecast_records if r['date'] == date), None)
            if record is None:
                record = {'date': date, 'train_end_date': str(train.index[-1].date()),
                    **forecasts, 'forecasts_by_method': {}, 'forecasts_by_strategy': {}, 'strategy_diagnostics': {},
                    'candidate_search': {}, 'mpt_fallback': None, 'overlay_fallback': False}
                forecast_records.append(record)
            if method != 'RISK_ONLY':
                record['forecasts_by_method'][method] = forecasts
                record.update(forecasts)
            record['forecasts_by_strategy'][name] = forecasts
            record['strategy_diagnostics'][name] = diagnostic
            record['candidate_search'][name] = decision.report
            if name == 'model_mpt': record['mpt_fallback'] = diagnostic['fallback_reason']
            if name == 'gmv_model': record['overlay_fallback'] = bool(diagnostic['fallback_reason'])
            pending['decision'] = decision
            return {'rebalance_date': date, 'models': {'min_variance': {'weights': weights,
                'diagnostics': {'construction_method': name, 'signal_scores': raw}}}}
        def completed(date, states):
            check()
            state = states['min_variance']
            pending['decision'].commit({'as_of': date, 'shares': state['shares'].to_dict(), 'cash': state['cash']})
            decisions.append(pending['decision'].report)
            config['campaign_id'] = campaign
            if checkpoint is not None:
                checkpoint(s)

        check()
        kwargs = {k: s[k] for k in ('train_window', 'rebalance_frequency', 'forecast_horizon',
                  'max_asset_weight', 'transaction_cost_bps', 'rebalance_band', 'max_turnover',
                  'risk_free_rate', 'initial_value')}
        run = run_portfolio_model_backtest(prices, models=['min_variance'],
            target_provider=provide, step_callback=completed,
            include_daily_returns=True, cancel_event=cancel_event, **kwargs)
        summary = run['summary_by_model']['min_variance']
        daily = pd.Series(run['daily_returns_by_model']['min_variance'], dtype=float).sort_index()
        expected = 1 + summary['net_cumulative_return']
        if not np.isclose((1+daily).prod(), expected, rtol=1e-9, atol=1e-9):
            raise ValueError('Daily returns do not reconcile with net wealth')
        first_trade = run['rebalance_records'][0]
        first_date = first_trade['rebalance_date']
        initial_ratio = first_trade['portfolio_value_after_cost'] / first_trade['portfolio_value_before_cost']
        # Split the combined first interval to show the actual initial cost date.
        daily.iloc[0] = (1 + daily.iloc[0]) / initial_ratio - 1
        daily = pd.concat([pd.Series({first_date: initial_ratio - 1}), daily])
        wealth = s['initial_value'] * (1+daily).cumprod()
        if not np.isclose(wealth.iloc[-1], s['initial_value'] * expected, rtol=1e-9, atol=1e-7):
            raise ValueError('Daily returns do not reconcile with net wealth')
        curve = {str(prices.index[s['train_window']-1].date()): s['initial_value'],
                 **{str(pd.Timestamp(d).date()): float(v) for d, v in wealth.items()}}
        values = pd.Series(curve)
        result['strategies'][name] = {'summary': summary, 'equity': curve,
            'drawdown': (values / values.cummax() - 1).to_dict(),
            'daily_returns': {str(pd.Timestamp(d).date()): float(v) for d, v in daily.items()},
            'rebalance_records': run['rebalance_records'], 'candidate_decisions': decisions, 'campaign_id': campaign}
        progress(5 + 90*(number+1)/len(s['strategies']), 100, f'Completed {name}')
    check()
    forecast_records.sort(key=lambda r: r['date'])
    result['price_digest'] = signature['price_digest']
    return json.loads(json.dumps(result, default=lambda value: value.item() if isinstance(value, np.generic) else str(value)))
