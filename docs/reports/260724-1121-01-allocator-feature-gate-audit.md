# Allocator and Feature Gate Audit

- 작성 일시: 2026-07-24 11:21 (KST)
- 상태: production/default 승격 없음
- 커밋: 목표 미달로 보류

## 목적

Execution truth 수정 이후에도 실제 optimizer 성능을 개선하는 frozen candidate가 있는지 fresh official data와 사전 고정 gate로 확인했습니다.

## Risk candidates

### Continuous trend risk parity

- Source: official French 38-industry daily archive에서 결측 source column 3개를 제외한 35개 complete portfolio
- Evaluation: `2000-01-03~2011-12-30`
- Candidate: 252일 log return / annualized volatility를 standard-normal CDF exposure로 변환
- Volatility: `21.05%→11.24%`
- Sharpe: `0.3041→0.2987`
- Drawdown: `-56.90%→-20.96%`
- P(lower volatility/higher Sharpe): `100%/45.35%`
- Decision: rejected

### Plain minvar independent replication

- Source: official French 35-industry, evaluation `2012~2017`
- Candidate Sharpe: `1.2318`
- Lightweight/risk-parity Sharpe: `1.2177/1.2072`
- P(higher Sharpe): `52.05%/53.60%`
- Decision: deterministic pass, statistical reject

### Minimum semivariance

- Candidate: historical downside semivariance, daily benchmark `0`, long-only capped fully-invested
- French 17-industry `2012~2017`: Sharpe `1.3485` vs minvar `1.3311`, P(higher Sharpe) `74.40%`
- Unchanged French 30-industry `2000~2011` replication: Sharpe `0.4397` vs minvar `0.4297`, P(lower volatility/higher Sharpe) `100%/69.35%`
- Decision: deterministic direction repeated, 95% gate rejected

### Minimum CDaR

- Candidate: historical CDaR `95%`, long-only capped fully-invested
- Source: official French 25 B/M×investment, evaluation `2000~2011`
- Candidate volatility/Sharpe/drawdown: `20.74%/0.2381/-56.73%`
- Minvar volatility/Sharpe/drawdown: `19.70%/0.3525/-55.88%`
- P(lower volatility/higher Sharpe): `0%/1.55%`
- Decision: deterministic, statistical, and Holm gates rejected

## Alpha features

### Long-term reversal momentum

- Download: official `25_Portfolios_ME_Prior_60_13_CSV.zip`, SHA-256 `fcbb8998…`
- Candidate: inverse prior 13–60 month return bucket 50% + 12–1 momentum 50%
- Evaluation: 16 annual OOS periods, `1983~1998`
- Candidate IC/spread: `0.1200/0.04394`
- P(IC>0): `90.05%`
- Paired P(higher IC/spread): `36.05%/68.70%`
- Decision: rejected

Daily variant `25_Portfolios_ME_Prior_60_13_Daily_CSV.zip` was downloaded and integrity-checked, but its numeric scale was inconsistent with the standard daily parser and the missing sentinel was ambiguous. It was not used in any result.

### Cashflow-yield momentum

- Download: official `Portfolios_Formed_on_CF-P_CSV.zip`, SHA-256 `0bfa77bb…`
- Candidate: CF/P decile 50% + 12–1 momentum 50%
- Evaluation: 30 annual OOS periods, `1969~1998`
- Candidate IC/spread: `0.0970/0.01776`
- Candidate P(IC>0/spread>0): `83.15%/75.55%`
- Paired P(higher IC/spread): `99.60%/99.95%`
- Decision: paired pass but absolute reject

### Pure cashflow yield

- Download: official `6_Portfolios_ME_CFP_2x3_CSV.zip`, SHA-256 `32b7a2ef…`
- Candidate: CF/P tercile 100%, momentum 0%
- Evaluation: 12 annual OOS periods, `2000~2011`
- Candidate IC/spread: `0.3287/0.06808`
- Absolute bootstrap: `100%/100%`
- Paired P(higher IC/spread): `80.05%/76.60%`
- Decision: high tie rate and paired gate reject

## Delisted-inclusive PIT data contract

- Added `tools/import_crsp_monthly_research_data.py` for licensed WRDS CRSP monthly stock and CCM/Compustat dated CIK-link exports.
- Required stock fields: `permno,date,ret,dlret,prc,shrout,shrcd,exchcd,ticker`.
- Required identity fields: `permno,cik,effective_start,effective_end`.
- Enforced invariants: common shares `SHRCD 10/11`, primary exchanges `EXCHCD 1/2/3`, permanent PERMNO keys, combined regular/delisting returns, non-overlapping PIT CIK intervals, full included-observation identity coverage, no leading fill.
- Outputs: monthly returns, wealth prices, market caps, historical universe events, SEC-compatible security master, and source/output SHA provenance.
- Licensed source exports are not present locally. No survivorship-biased substitute was downloaded or used.

## 결론

- Engine accounting, exposure, executable-price, and transaction-cost invariants are materially improved.
- Default optimization model performance is not yet quant-standard: no candidate passed research, validation, and locked holdout.
- Transformer hyperparameter tuning remains unsupported because cross-sectional target ordering is the bottleneck.
- Next credible alpha step requires canonical/licensed delisted-inclusive PIT prices and issuer identity. Reusing survivorship-biased public prices would invalidate promotion evidence.

## Verification

- Risk allocator focused tests: `48 passed`
- Characteristic research focused tests: `9 passed`
- CRSP importer focused tests: `5 passed`
- Full backend regression: `351 passed`
- Locked split self-hashes, source/price provenance SHA, and ZIP integrity checks passed.
