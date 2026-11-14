"""Durable, as-of candidate selection. Search snapshots never become current views."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

import numpy as np
import pandas as pd

POLICY_VERSION = 'candidate-search-v1'
PRICE_CACHE_RTOL = 5e-7
PRICE_CACHE_ATOL = 1e-8

MODES = ('forecast_profile', 'price_features', 'frozen_forecast')
DEFAULTS = dict(enabled=True, mode='forecast_profile', similar_count=10, explore_count=10,
                seed=42, refresh_interval=252)


class CandidateSearchError(ValueError):
    def to_dict(self):
        return {'error': str(self), 'error_code': 'CANDIDATE_SEARCH_FAILED'}


def normalize_policy(value=None):
    if value is None:
        return dict(DEFAULTS)
    if not isinstance(value, dict):
        raise ValueError('candidate_search must be an object')
    policy = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in value:
            policy[key] = value[key]
    if not isinstance(policy['enabled'], bool) or policy['mode'] not in MODES:
        raise ValueError('Invalid candidate search enabled/mode')
    for key, high in [('similar_count', 2000), ('explore_count', 2000), ('seed', 2**32-1), ('refresh_interval', 2520)]:
        number = policy[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not np.isfinite(number) or int(number) != number or not (1 if key == 'refresh_interval' else 0) <= number <= high:
            raise ValueError('Invalid candidate search ' + key)
        policy[key] = int(number)
    return policy


def _safe(value):
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _dump(value):
    return json.dumps(_safe(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_dump(value).encode()).hexdigest()


def _standardize(frame):
    frame = pd.DataFrame(frame, dtype=float)
    scale = frame.quantile(.75) - frame.quantile(.25)
    axes = scale.index[scale > 1e-12]
    return ((frame[axes] - frame[axes].median()) / scale[axes]) if len(axes) else pd.DataFrame(index=frame.index)


def _neighbors(prices, snapshot, held, mode, count):
    if not held or count == 0:
        return []
    available = sorted(set(prices.columns) - set(held))
    if mode != 'price_features':
        entries = {t: [p.get('expected_return'), p.get('uncertainty')] for t, p in snapshot.items()
                   if p.get('expected_return') is not None and p.get('uncertainty') is not None}
        frame = pd.DataFrame.from_dict(entries, orient='index').replace([np.inf, -np.inf], np.nan).dropna()
        z = _standardize(frame)
        reference = sorted(set(held) & set(z.index))
        if z.shape[1] == 0 or not reference:
            return []
        scores = {t: -float(np.min(np.linalg.norm(z.loc[reference].to_numpy() - z.loc[t].to_numpy(), axis=1)))
                  for t in available if t in z.index}
    else:
        returns = np.log(prices).diff().dropna(how='all')
        market = returns.mean(axis=1).tail(126)
        var = market.var()
        features = pd.DataFrame(index=prices.columns)
        features['momentum21'] = prices.iloc[-1] / prices.iloc[-min(22, len(prices))] - 1
        features['momentum63'] = prices.iloc[-1] / prices.iloc[-min(64, len(prices))] - 1
        features['volatility63'] = returns.tail(63).std()
        features['beta126'] = returns.tail(126).apply(lambda x: x.cov(market) / var if var > 1e-15 else 0.)
        z = _standardize(features).fillna(0.)
        norms = np.linalg.norm(z.to_numpy(), axis=1)
        normalized = z.div(pd.Series(norms, index=z.index).replace(0, np.nan), axis=0).fillna(0.)
        corr = returns.tail(60).corr()
        reference = sorted(set(held) & set(prices.columns))
        scores = {}
        for ticker in available:
            similarities = []
            for h in reference:
                shape = corr.loc[ticker, h]
                state = float(normalized.loc[ticker].dot(normalized.loc[h]))
                similarities.append(.5 * (shape if np.isfinite(shape) else 0.) + .5 * state)
            if similarities:
                scores[ticker] = max(similarities)
    return sorted(scores, key=lambda t: (-scores[t], t))[:count]


class CandidateStore:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('ANTIFIER_CANDIDATE_DB', 'logs/candidate_search/state.sqlite3'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS campaigns(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    revision INTEGER NOT NULL, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions(campaign TEXT, key TEXT, payload TEXT NOT NULL,
                    PRIMARY KEY(campaign,key));
                CREATE TABLE IF NOT EXISTS predictions(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prediction_inputs(key TEXT PRIMARY KEY, family TEXT NOT NULL,
                    prices BLOB NOT NULL);
                CREATE INDEX IF NOT EXISTS prediction_inputs_family ON prediction_inputs(family);
            ''')

    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=30)
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def inspect(self, campaign_id):
        if campaign_id is None:
            return None
        if not isinstance(campaign_id, str) or not __import__('re').fullmatch(r'[a-f0-9]{32}', campaign_id):
            raise CandidateSearchError('Invalid candidate search campaign_id')
        with self.connect() as db:
            row = db.execute('SELECT fingerprint,revision,state FROM campaigns WHERE id=?', (campaign_id,)).fetchone()
        if row is None:
            raise CandidateSearchError('Candidate campaign not found; create a new campaign')
        return row[0], row[1], json.loads(row[2])

    def is_committed(self, campaign_id, key):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM decisions WHERE campaign=? AND key=?',
                              (campaign_id, key)).fetchone() is not None

    def lookup_prediction(self, key, family, values):
        values = np.asarray(values, dtype='<f8')
        with self.connect() as db:
            exact = db.execute('SELECT payload FROM predictions WHERE key=?', (key,)).fetchone()
            if exact:
                # Legacy exact hits can safely acquire their missing input provenance.
                db.execute('INSERT OR IGNORE INTO prediction_inputs VALUES (?,?,?)',
                           (key, family, values.tobytes()))
                return json.loads(exact[0]), False
            matches = db.execute('SELECT i.prices,p.payload FROM prediction_inputs i JOIN predictions p '
                                 'ON i.key=p.key WHERE i.family=? ORDER BY i.rowid', (family,)).fetchall()
        for raw, payload in matches:
            original = np.frombuffer(raw, dtype='<f8')
            if original.shape == values.shape and np.allclose(values, original,
                    rtol=PRICE_CACHE_RTOL, atol=PRICE_CACHE_ATOL, equal_nan=False):
                return json.loads(payload), True
        return None, False

    def prepare(self, prices, holdings, policy=None, *, method, horizon, train_window,
                forecast, campaign_id=None, required=(), cancel_event=None, progress=None, batch_forecast=None):
        from portfolio_optimization import _raise_if_cancelled
        from direct_horizon_forecast import MODEL_VERSION
        policy = normalize_policy(policy)
        _raise_if_cancelled(cancel_event)
        prices = prices.copy().sort_index()
        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        if prices.empty or prices.index.has_duplicates or prices.isna().any().any() or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
            raise CandidateSearchError('Candidate selection requires complete positive as-of prices')
        universe = sorted(prices.columns)
        held = sorted(t for t, value in holdings.items() if float(value) > 0)
        mandatory = sorted(set(required))
        if set(held + mandatory) - set(universe):
            raise CandidateSearchError('Held or required assets are missing from the price universe')
        mode = 'price_features' if method == 'RISK_ONLY' else policy['mode']
        identity = dict(policy=policy, mode=mode, universe=universe, method=method,
                        horizon=horizon, train_window=train_window, version=POLICY_VERSION, model=MODEL_VERSION)
        fingerprint = _digest(identity)
        old = self.inspect(campaign_id)
        reset_from = None
        if old is not None and old[0] != fingerprint:
            reset_from, campaign_id, old = campaign_id, None, None
        campaign_id = campaign_id or uuid.uuid4().hex
        revision = old[1] if old else 0
        state = copy.deepcopy(old[2]) if old else dict(snapshot={}, map_as_of=None, queue=[], cycle=0)
        as_of = str(prices.index[-1].date())
        history_hash = hashlib.sha256(prices.to_numpy().tobytes() + prices.index.asi8.tobytes()).hexdigest()
        key = _digest(dict(as_of=as_of, history=history_hash, held={t: float(holdings[t]) for t in held}, required=mandatory))
        with self.connect() as db:
            previous = db.execute('SELECT payload FROM decisions WHERE campaign=? AND key=?', (campaign_id, key)).fetchone()
        if previous:
            return Prepared(self, campaign_id, fingerprint, revision, state, key, json.loads(previous[0]), replay=True)
        if state.get('last_as_of') and state['last_as_of'] > as_of:
            raise CandidateSearchError('Cannot rewind a campaign; use a new campaign for historical analysis')
        counts = dict(prediction_calls=0, cache_hits=0, compatible_cache_hits=0, failures=0)
        started = time.monotonic()
        predictions = {}
        batch_values = {}
        def cache_key(ticker):
            series = prices[ticker].tail(train_window)
            return _digest(dict(ticker=ticker, method=method, horizon=horizon,
                model=MODEL_VERSION, history=hashlib.sha256(series.to_numpy().tobytes() + series.index.asi8.tobytes()).hexdigest()))
        cached_predictions = {}
        def lookup(ticker):
            if ticker not in cached_predictions:
                series = prices[ticker].tail(train_window)
                family = _digest(dict(ticker=ticker, method=method, horizon=horizon, model=MODEL_VERSION,
                                      dates=series.index.asi8.tolist()))
                cached_predictions[ticker] = (family, *self.lookup_prediction(cache_key(ticker), family, series.to_numpy()))
            return cached_predictions[ticker]
        def predict_many(tickers, stage):
            tickers = [t for t in tickers if t not in predictions]
            if not tickers:
                return
            before = counts.copy()
            def notify(ticker, done):
                if progress:
                    progress(dict(stage=stage, ticker=ticker, done=done, total=len(tickers),
                        universe_count=len(universe), prediction_calls=counts['prediction_calls'] - before['prediction_calls'],
                        cache_hits=counts['cache_hits'] - before['cache_hits']))
            notify(None, 0)
            if batch_forecast is not None:
                missing = [t for t in tickers if t not in predictions and lookup(t)[1] is None]
                if missing:
                    batch_values.update(batch_forecast(prices[missing].tail(train_window), horizon))
            for done, ticker in enumerate(tickers, 1):
                predict(ticker)
                notify(ticker, done)
        def predict(ticker):
            _raise_if_cancelled(cancel_event)
            if ticker in predictions:
                return predictions[ticker]
            series = prices[ticker].tail(train_window)
            prediction_key = cache_key(ticker)
            family, cached, compatible = lookup(ticker)
            if cached is not None:
                value = cached
                counts['cache_hits'] += 1
                counts['compatible_cache_hits'] += int(compatible)
            else:
                value = _safe(batch_values[ticker] if ticker in batch_values else forecast(ticker, series, horizon))
                if not isinstance(value, dict):
                    raise CandidateSearchError('Forecast returned an invalid result')
                with self.connect() as db:
                    db.execute('INSERT OR IGNORE INTO predictions VALUES (?,?)', (prediction_key, _dump(value)))
                    db.execute('INSERT OR IGNORE INTO prediction_inputs VALUES (?,?,?)',
                               (prediction_key, family, np.asarray(series.to_numpy(), dtype='<f8').tobytes()))
                counts['prediction_calls'] += 1
            if value.get('expected_return') is None:
                counts['failures'] += 1
            predictions[ticker] = value
            return value
        initial = old is None or not held
        elapsed = 0
        calendar_gap = False
        if state['map_as_of']:
            last_date = pd.Timestamp(state.get('last_as_of') or state['map_as_of'])
            elapsed = state.get('map_age_sessions', 0) + int((prices.index > last_date).sum())
            calendar_gap = last_date < prices.index[0]
        refresh = initial or (mode == 'forecast_profile' and (elapsed >= policy['refresh_interval'] or calendar_gap))
        full = not policy['enabled'] or refresh
        if method != 'RISK_ONLY' and (full or (mode != 'price_features' and not state['snapshot'])):
            predict_many(universe, 'initial_map' if initial else 'full_refresh')
            if mode != 'price_features':
                state['snapshot'] = copy.deepcopy(predictions)
                state['map_as_of'] = as_of
        if mode == 'price_features':
            state['map_as_of'] = as_of
        similar = [] if full else _neighbors(prices, state['snapshot'], held, mode, policy['similar_count'])
        random = []
        if full:
            state['queue'] = []
            state['cycle'] += 1
        else:
            if not state['queue']:
                state['cycle'] += 1
                seed = np.random.SeedSequence([policy['seed'], state['cycle']])
                state['queue'] = list(np.random.default_rng(seed).permutation(universe))
            already = set(held + similar + mandatory)
            while state['queue'] and len(random) < policy['explore_count']:
                ticker = state['queue'].pop(0)
                if ticker not in already:
                    random.append(ticker); already.add(ticker)
        selected = universe if full else sorted(set(held + similar + random + mandatory))
        if not selected:
            raise CandidateSearchError('No candidates available')
        if method != 'RISK_ONLY':
            predict_many(selected, 'current_forecasts' if full else 'partial_refresh')
        state['map_age_sessions'] = 0 if state['map_as_of'] == as_of else elapsed
        state['last_as_of'] = as_of
        state['identity'] = identity
        report = dict(campaign_id=campaign_id, decision_key=key, policy=policy, mode_effective=mode,
            full_refresh=full, initial=initial, reset_from=reset_from, as_of=as_of,
            map_as_of=state['map_as_of'], map_age_sessions=0 if state['map_as_of']==as_of else elapsed,
            held=held, similar=similar, random=random, required=mandatory, selected=selected,
            universe_count=len(universe), selected_count=len(selected), cycle=state['cycle'],
            remaining_in_cycle=len(state['queue']), estimated_cycle_steps=int(np.ceil(len(universe)/max(1,policy['explore_count']))),
            limited_savings=len(selected) >= .8 * len(universe), elapsed_seconds=time.monotonic()-started,
            failures_by_ticker={t: predictions[t] for t in selected if t in predictions and predictions[t].get('expected_return') is None},
            **counts)
        payload = dict(report=report, predictions={t: predictions[t] for t in selected if t in predictions})
        return Prepared(self, campaign_id, fingerprint, revision, state, key, payload)


class Prepared:
    def __init__(self, store, campaign_id, fingerprint, revision, state, key, payload, replay=False):
        self.committed = False
        self.store, self.campaign_id, self.fingerprint = store, campaign_id, fingerprint
        self.revision, self.state, self.key, self.payload, self.replay = revision, state, key, payload, replay

    @property
    def report(self):
        value = dict(self.payload['report'])
        if self.replay:
            value.update(prediction_calls=0, cache_hits=0, compatible_cache_hits=0, failures=0, elapsed_seconds=0., replayed=True)
        return value

    @property
    def predictions(self):
        return self.payload['predictions']

    def commit(self, completion=None, cancel_event=None):
        from portfolio_optimization import _raise_if_cancelled
        _raise_if_cancelled(cancel_event)
        if self.replay or self.committed:
            return
        payload = dict(self.payload, completion=completion)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            _raise_if_cancelled(cancel_event)
            row = db.execute('SELECT revision FROM campaigns WHERE id=?', (self.campaign_id,)).fetchone()
            if (row[0] if row else 0) != self.revision:
                raise CandidateSearchError('Campaign changed concurrently; retry this decision')
            db.execute('INSERT OR REPLACE INTO campaigns VALUES (?,?,?,?)',
                       (self.campaign_id, self.fingerprint, self.revision+1, _dump(self.state)))
            db.execute('INSERT OR REPLACE INTO decisions VALUES (?,?,?)',
                       (self.campaign_id, self.key, _dump(payload)))
        self.committed = True


def live_hook(policy, method, horizon, window, holdings, campaign_id, required, cancel_event, progress):
    """Adapt the existing production batch forecasters without changing allocation semantics."""
    import portfolio_optimization as p
    context = {}
    def select(data):
        frame = data.tail(window).replace([np.inf, -np.inf], np.nan).dropna(axis=1)
        held = {t: v for t, v in holdings.items() if float(v) > 0}
        if set(held) - set(frame.columns):
            raise CandidateSearchError('A held asset is missing valid as-of prices')
        def batch(prices, h):
            if method in {'TRANSFORMER', 'ARIMA_TRANSFORMER'}:
                function = p.transformer_forecast_returns if method == 'TRANSFORMER' else p.ml_forecast_returns
                means, uncertainty = function(prices, progress_callback=progress, horizon=h, cancel_event=cancel_event)
                return {t: {'expected_return': None if pd.isna(means.get(t)) else float(means[t]),
                            'uncertainty': float(uncertainty.get(t, p.MAX_FORECAST_UNCERTAINTY)),
                            'source': 'no_view' if pd.isna(means.get(t)) else method.lower(),
                            'reason': 'no_usable_view; see forecast logs' if pd.isna(means.get(t)) else None}
                        for t in prices.columns}
            result = {}
            for ticker in prices:
                p._raise_if_cancelled(cancel_event)
                if method == 'HISTORICAL':
                    mean = float(p._calculate_historical_cagr(prices[[ticker]])[ticker])
                    annual = float(np.log1p(max(mean, -.99)))
                else:
                    period = p.lightweight_ensemble_forecast(prices[ticker].to_numpy(), horizon=h)
                    annual = float(np.log1p(period) * 252 / h)
                result[ticker] = {'expected_return': annual, 'uncertainty': p.DEFAULT_FORECAST_UNCERTAINTY,
                                  'source': method.lower()}
            return result
        decision = CandidateStore().prepare(frame, held, policy, method=method, horizon=horizon,
            train_window=window, forecast=lambda *a: None, batch_forecast=batch,
            campaign_id=campaign_id, required=required, cancel_event=cancel_event)
        context['decision'] = decision
        return frame[decision.report['selected']], decision.predictions
    return select, context
