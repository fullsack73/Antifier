import threading
import numpy as np
import pandas as pd
import pytest
from candidate_search import CandidateStore, normalize_policy, CandidateSearchError

@pytest.fixture
def setup(tmp_path):
    rng=np.random.default_rng(42)
    prices=pd.DataFrame(100*np.exp(np.cumsum(rng.normal(0,.01,(600,500)),axis=0)),
        index=pd.bdate_range('2021-01-01',periods=600),columns=[f'T{i:03}' for i in range(500)])
    calls=[]
    def predict(t, s, h):
        calls.append((t,s.index[-1]))
        return {'expected_return': float(int(t[1:])/500), 'uncertainty': .1+int(t[1:])/1000}
    return CandidateStore(tmp_path/'state.sqlite'), prices, calls, predict

def prepare(setup, *, end=200, holdings=None, campaign_id=None, policy=None):
    store,prices,_,forecast=setup
    return store.prepare(prices.iloc[:end].tail(504),holdings or {},policy,method='TRANSFORMER',
        horizon=63,train_window=126,forecast=forecast,campaign_id=campaign_id)

def test_500_to_40_and_restart(setup):
    first=prepare(setup);assert len(first.report['selected'])==500
    first.commit()
    held={f'T{i:03}':1 for i in range(20)}
    next_=prepare(setup,end=221,holdings=held,campaign_id=first.campaign_id)
    assert set(held)<=set(next_.report['selected'])
    assert len(next_.report['similar'])==10 and len(next_.report['random'])==10
    assert next_.report['prediction_calls']==40
    next_.commit()
    replay=prepare(setup,end=221,holdings=held,campaign_id=first.campaign_id)
    assert replay.report['selected']==next_.report['selected']
    assert len(setup[2])==540

def test_cancelled_or_uncommitted_queue_does_not_advance(setup):
    first=prepare(setup);first.commit()
    held={'T000':1}
    aborted=prepare(setup,end=221,holdings=held,campaign_id=first.campaign_id)
    retry=prepare(setup,end=221,holdings=held,campaign_id=first.campaign_id)
    assert aborted.report['random']==retry.report['random']
    retry.commit()
    following=prepare(setup,end=242,holdings=held,campaign_id=first.campaign_id)
    assert not set(retry.report['random']) & set(following.report['random'])

def test_refresh_and_frozen_maps(setup):
    for mode in ['forecast_profile','frozen_forecast']:
        first=prepare(setup,policy={'mode':mode});first.commit()
        next_=prepare(setup,end=452,holdings={'T000':1},campaign_id=first.campaign_id,policy={'mode':mode})
        assert next_.report['full_refresh']==(mode=='forecast_profile')

def test_settings_change_creates_new_context_and_history_cannot_rewind(setup):
    first=prepare(setup);first.commit()
    changed=prepare(setup,end=221,holdings={'T000':1},campaign_id=first.campaign_id,policy={'seed':43})
    assert changed.campaign_id != first.campaign_id and changed.report['reset_from']==first.campaign_id
    later=prepare(setup,end=242,holdings={'T000':1},campaign_id=first.campaign_id);later.commit()
    with pytest.raises(CandidateSearchError,match='rewind'):
        prepare(setup,end=200,holdings={'T001':1},campaign_id=first.campaign_id)

def test_risk_only_never_forecasts(setup):
    store,prices,_,_=setup
    def forbidden(*a):raise AssertionError()
    d=store.prepare(prices.iloc[:200],{},method='RISK_ONLY',horizon=63,train_window=126,forecast=forbidden)
    assert d.report['mode_effective']=='price_features' and d.report['prediction_calls']==0

@pytest.mark.parametrize('p',[{'enabled':'true'},{'mode':'bad'},{'explore_count':-1},{'seed':True}])
def test_policy_validation(p):
    with pytest.raises(ValueError):normalize_policy(p)


def test_cancel_before_commit_and_concurrent_commit_are_atomic(setup):
    from portfolio_optimization import OptimizationCancelled
    d=prepare(setup); event=threading.Event();event.set()
    with pytest.raises(OptimizationCancelled):d.commit(cancel_event=event)
    with pytest.raises(CandidateSearchError,match='not found'):setup[0].inspect(d.campaign_id)
    d.commit()
    first=prepare(setup,end=221,holdings={'T000':1},campaign_id=d.campaign_id)
    conflict=prepare(setup,end=221,holdings={'T001':1},campaign_id=d.campaign_id)
    first.commit()
    saved=setup[0].inspect(d.campaign_id)
    with pytest.raises(CandidateSearchError,match='concurrently'):conflict.commit()
    assert setup[0].inspect(d.campaign_id)==saved


def test_future_changes_do_not_change_selection_and_required_assets_survive(setup):
    a=prepare(setup);a.commit()
    setup[1].iloc[221:] *= 3
    held={f'T{i:03}':1 for i in range(20)}
    b=prepare(setup,end=221,holdings=held,campaign_id=a.campaign_id)
    setup[1].iloc[221:] *= 2
    c=prepare(setup,end=221,holdings=held,campaign_id=a.campaign_id)
    assert b.report['selected']==c.report['selected']
    d=setup[0].prepare(setup[1].iloc[:221],held,method='TRANSFORMER',horizon=63,
        train_window=126,forecast=setup[3],campaign_id=a.campaign_id,required=['T499'])
    assert 'T499' in d.report['selected']


def test_no_holdings_cap_and_replay_reports_no_new_calls(setup):
    first=prepare(setup);first.commit()
    held={t:1 for t in setup[1].columns}
    d=prepare(setup,end=221,holdings=held,campaign_id=first.campaign_id)
    assert len(d.report['selected'])==500 and d.report['limited_savings']
    d.commit()
    replay=prepare(setup,end=221,holdings=held,campaign_id=first.campaign_id)
    assert replay.report['prediction_calls']==0 and replay.report['replayed']


def test_malformed_forecasts_do_not_create_fake_neighbors(setup):
    store,prices,_,_=setup
    def invalid(*a):return {'expected_return':None,'uncertainty':None,'source':'no_view'}
    d=store.prepare(prices.iloc[:200],{},method='TRANSFORMER',horizon=63,train_window=126,forecast=invalid)
    d.commit()
    next_=store.prepare(prices.iloc[:221],{'T000':1},method='TRANSFORMER',horizon=63,train_window=126,
                        forecast=invalid,campaign_id=d.campaign_id)
    assert next_.report['similar']==[] and len(next_.report['random'])==10


def test_live_hook_reuses_batch_forecaster_and_cache(setup, monkeypatch):
    from candidate_search import live_hook
    import portfolio_optimization as po
    calls=[]
    def batch(frame, **kwargs):
        calls.append(len(frame.columns))
        return pd.Series(np.arange(len(frame.columns))*.001,index=frame.columns), pd.Series(.2,index=frame.columns)
    monkeypatch.setattr(po, 'transformer_forecast_returns', batch)
    first, context=live_hook({}, 'TRANSFORMER',63,200,{},None,(),None,None)
    frame, forecasts=first(setup[1].iloc[:200]); context['decision'].commit()
    second, next_context=live_hook({},'TRANSFORMER',63,200,{'T000':1},context['decision'].campaign_id,(),None,None)
    subset,_=second(setup[1].iloc[:221])
    assert calls==[500,21] and len(subset.columns)==21 and len(forecasts)==500
    third,_=live_hook({},'TRANSFORMER',63,200,{'T000':1},context['decision'].campaign_id,(),None,None)
    third(setup[1].iloc[:221])
    assert calls==[500,21]


def test_preview_detects_settings_changes(setup, monkeypatch):
    import app
    monkeypatch.setenv('ANTIFIER_CANDIDATE_DB', str(setup[0].path))
    initial=prepare(setup);initial.commit()
    payload={'campaign_id':initial.campaign_id,'tickers':list(setup[1].columns),
             'holdings':{'T000':1},'forecast_method':'TRANSFORMER','candidate_search':{'seed':43}}
    response=app.app.test_client().post('/api/candidate-search/preview',json=payload)
    assert response.status_code==200 and response.json['reset_required'] and response.json['initial']


def test_refresh_counts_sessions_across_short_training_windows(setup):
    store,prices,_,forecast=setup
    def step(end,campaign=None):
        return store.prepare(prices.iloc[:end].tail(126),{'T000':1},method='TRANSFORMER',horizon=63,
            train_window=126,forecast=forecast,campaign_id=campaign)
    first=step(200);first.commit()
    for end,age in [(263,63),(326,126),(389,189),(452,0)]:
        decision=step(end,first.campaign_id)
        assert decision.report['map_age_sessions']==age
        assert decision.report['full_refresh']==(end==452)
        decision.commit()


def test_random_cycle_exhaustion_and_seed_reproducibility(setup):
    store,prices,_,forecast=setup
    prices=prices.iloc[:,:6]
    policy={'similar_count':0,'explore_count':3,'mode':'frozen_forecast'}
    def step(end,campaign=None):
        return store.prepare(prices.iloc[:end],{'T000':1},policy,method='TRANSFORMER',horizon=63,
            train_window=126,forecast=forecast,campaign_id=campaign)
    initial=step(200);initial.commit()
    a=step(221,initial.campaign_id);a.commit()
    b=step(242,initial.campaign_id);b.commit()
    assert len(a.report['random'])==3 and len(b.report['random'])==2
    assert not set(a.report['random']) & set(b.report['random'])
    assert b.report['remaining_in_cycle']==0
    c=step(263,initial.campaign_id)
    assert c.report['cycle']==b.report['cycle']+1 and len(c.report['random'])==3
    another=step(200);another.commit()
    assert step(221,another.campaign_id).report['random']==a.report['random']


def test_saved_result_is_not_visible_until_candidate_transaction_commits(setup, monkeypatch, tmp_path):
    import portfolio_optimization as po
    monkeypatch.setenv('ANTIFIER_CANDIDATE_DB',str(setup[0].path))
    monkeypatch.setattr(po,'RESULTS_DIR',tmp_path/'results')
    d=prepare(setup)
    po.save_portfolio_result('candidate-fixture',{'weights':{},'candidate_search':d.report})
    assert po.load_portfolio_result('candidate-fixture') is None
    d.commit()
    assert po.load_portfolio_result('candidate-fixture')['candidate_search']['decision_key']==d.key


def test_micro_price_revisions_reuse_forecasts_without_chaining(setup):
    store,prices,calls,forecast=setup
    frame=prices.iloc[:200,:3].copy()
    def run(data,**kwargs):
        return store.prepare(data,{},method='TRANSFORMER',horizon=63,train_window=126,
                             forecast=forecast,**kwargs)
    first=run(frame)
    tiny=frame*(1+4e-7)
    reused=run(tiny)
    assert len(calls)==3 and reused.report['prediction_calls']==0
    assert reused.report['cache_hits']==reused.report['compatible_cache_hits']==3
    assert reused.predictions==first.predictions
    # Two individually small changes cannot move the anchor used to validate reuse.
    changed=run(frame*(1+8e-7))
    assert changed.report['prediction_calls']==3 and len(calls)==6
    assert store.connect().execute('select count(*) from prediction_inputs').fetchone()[0]==6


def test_revised_dates_horizon_model_and_material_prices_do_not_share(setup,monkeypatch):
    import direct_horizon_forecast as direct
    store,prices,calls,forecast=setup
    frame=prices.iloc[:200,:2]
    def run(data,horizon=63):
        return store.prepare(data,{},method='TRANSFORMER',horizon=horizon,train_window=126,forecast=forecast)
    run(frame)
    shifted=frame.copy();shifted.index+=pd.Timedelta(days=1)
    assert run(shifted).report['cache_hits']==0
    assert run(frame,horizon=21).report['cache_hits']==0
    assert run(frame*1.001).report['cache_hits']==0
    monkeypatch.setattr(direct,'MODEL_VERSION','new-model')
    assert run(frame).report['cache_hits']==0


def test_legacy_cache_inputs_are_only_backfilled_on_an_exact_match(setup):
    store,prices,calls,forecast=setup
    frame=prices.iloc[:200,:2]
    def run(data):
        return store.prepare(data,{},method='TRANSFORMER',horizon=63,train_window=126,forecast=forecast)
    run(frame)
    with store.connect() as db:db.execute('delete from prediction_inputs')
    assert run(frame).report['cache_hits']==2
    assert len(calls)==2
    assert run(frame*(1+1e-7)).report['compatible_cache_hits']==2


def test_batch_cache_lookup_does_not_train_compatible_inputs(setup):
    store,prices,_,forecast=setup
    frame=prices.iloc[:200,:3]
    store.prepare(frame,{},method='TRANSFORMER',horizon=63,train_window=126,forecast=forecast)
    def forbidden(*a):raise AssertionError('must reuse compatible inputs before batching')
    d=store.prepare(frame*(1+1e-7),{},method='TRANSFORMER',horizon=63,train_window=126,
                    forecast=forbidden,batch_forecast=forbidden)
    assert d.report['compatible_cache_hits']==3 and d.report['prediction_calls']==0


@pytest.mark.parametrize('mode', ['frozen_forecast', 'forecast_profile'])
def test_progress_tracks_actual_phase_and_all_cache_hits(setup, mode):
    store, prices, calls, forecast = setup
    prices = prices.iloc[:, :457]
    events = []
    def run(end, holdings, campaign=None):
        return store.prepare(prices.iloc[:end], holdings, {'mode': mode}, method='TRANSFORMER',
            horizon=63, train_window=126, forecast=forecast, campaign_id=campaign, progress=events.append)
    first = run(200, {})
    assert events[0]['stage'] == 'initial_map'
    assert events[-1]['done'] == events[-1]['total'] == 457
    first.commit()
    events.clear()
    held = {f'T{i:03}': 1 for i in range(20)}
    partial = run(221, held, first.campaign_id)
    assert partial.report['selected_count'] == 40
    assert {e['total'] for e in events} == {40}
    assert {e['universe_count'] for e in events} == {457}
    assert {e['stage'] for e in events} == {'partial_refresh'}
    assert events[-1]['prediction_calls'] == events[-1]['done'] == 40
    # Retrying an uncommitted step must also emit a completed, entirely cached phase.
    events.clear()
    run(221, held, first.campaign_id)
    assert events[-1]['cache_hits'] == events[-1]['done'] == 40
    assert events[-1]['prediction_calls'] == 0
    # Mixed cache: removing one selected forecast causes exactly one new call.
    with store.connect() as db:
        db.execute("DELETE FROM predictions WHERE key IN (SELECT key FROM prediction_inputs WHERE family IN "
                   "(SELECT family FROM prediction_inputs) ORDER BY rowid DESC LIMIT 1)")
    events.clear()
    run(221, held, first.campaign_id)
    assert events[-1]['cache_hits'] == 39 and events[-1]['prediction_calls'] == 1
    events.clear()
    run(452, held, first.campaign_id)
    assert events[-1]['stage'] == ('full_refresh' if mode == 'forecast_profile' else 'partial_refresh')
    assert events[-1]['total'] == (457 if mode == 'forecast_profile' else 40)
