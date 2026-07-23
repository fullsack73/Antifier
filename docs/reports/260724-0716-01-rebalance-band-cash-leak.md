# Rebalance-Band Cash Leak Fix

## 결정

- 2% 절대 rebalance band가 매수와 매도를 독립적으로 제거해 fully-invested
  target에서도 현금을 누적시키는 결함을 수정했습니다.
- band 적용 후 target의 의도된 net trade와 risky/cash exposure를 보존하도록
  필요한 최소 반대편 skipped trade를 재도입합니다.
- 그 다음 기존 gross-turnover cap과 available-cash guard를 적용합니다.
- Forecast, covariance, optimizer objective는 변경하지 않았습니다.

## 발견 경로

변경 전 plain Ledoit-Wolf minimum variance를 미사용 official French
49-industry early-history universe에서 독립 복제했습니다.

- raw source: Kenneth R. French 49 Industry Portfolios Daily
- raw SHA-256:
  `e214c54a41f058c03ed4a4e582b2126e04120d2a84bc19c023bd2a4251f77097`
- panel: 1926-07-01~1969-12-31, 12,030 rows × 36 complete industries
- evaluation: 1928-03-07~1969-12-31
- split digest:
  `99ff9798dd9843282792847aab0f90d0bd46e2ab98d71e0ec78e58c0b07dcdeb`
- prior candidate specification: unchanged

Pre-fix replication에서 minvar는 deterministic gate와 risk-parity 비교를
통과했지만 lightweight 대비 higher-Sharpe probability가 `86.70%`여서 사전
95% gate를 통과하지 못했습니다.

| Model | CAGR | Volatility | Sharpe | Mean cash |
|---|---:|---:|---:|---:|
| Lightweight BL | 9.53% | 16.95% | 0.5373 | 1.86% |
| Risk parity | 8.10% | 15.33% | 0.4912 | 8.02% |
| Minimum variance | 8.53% | 12.27% | 0.6119 | 0.29% |

Candidate는 승격하지 않습니다. 이 실행에서 execution bug를 발견했으므로
result는 default promotion 근거가 아니라 bug-discovery lineage로만 보존합니다.
이미 결과를 본 split을 post-fix 승격 판정에 재사용하지 않습니다.

## 재현과 수정

예: 현재 `[400, 300, 300]`, target `[430, 285, 285]`, portfolio
`1,000`, band `2%`.

- 기존: `+30` 매수만 실행, `-15/-15` 매도는 각각 band 아래라 제거
- 결과: self-financing 위반 또는 available-cash 보정으로 target 왜곡
- 수정: 두 skipped 매도를 최소한으로 재도입해 net trade `0` 유지

새 diagnostics:

- `band_reintroduced_trade_count`
- `desired_net_trade_value`
- `post_control_net_trade_value`

## Post-fix execution diagnostic

같은 이미 본 panel은 promotion 통계에 재사용하지 않고 mechanical
before/after diagnostic에만 사용했습니다.

| Model | Mean cash before | Mean cash after | CAGR before | CAGR after | Sharpe before | Sharpe after |
|---|---:|---:|---:|---:|---:|---:|
| Equal weight | 14.55% | 0.0015% | 8.20% | 9.16% | 0.5072 | 0.5005 |
| Historical BL | 3.15% | 0.0021% | 9.07% | 9.13% | 0.5080 | 0.5041 |
| Lightweight BL | 1.86% | 0.0205% | 9.53% | 9.80% | 0.5373 | 0.5514 |
| Risk parity | 8.02% | 0.0020% | 8.10% | 9.07% | 0.4912 | 0.5146 |
| Minimum variance | 0.29% | 0.0153% | 8.53% | 8.45% | 0.6119 | 0.6116 |

Fully-invested target의 unintentional cash drag가 사실상 제거됐습니다. 일부
저위험 모델의 Sharpe 변화는 현금 노출이 사라져 위험이 함께 증가한 결과이며,
숨은 현금으로 성과를 보정하지 않습니다.

## 검증

- asymmetric band cash-exposure regression 추가
- 기존 symmetric band 및 turnover-cap 동작 유지
- post-fix cash exposure diagnostic 실행
- frozen pre-fix replication result는 덮어쓰지 않음
