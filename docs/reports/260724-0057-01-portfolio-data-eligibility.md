# Portfolio Data Eligibility Policy

- 작업 일시: 2026-07-24 00:57 (KST)
- 상태: 완료

## 결정

- `min_history` 미만 ticker는 최적화 universe에서 제외합니다.
- 성공과 데이터 준비 오류 모두 `data_eligibility`를 반환합니다.
- 요청 ticker별 관측 수, 요청 window 커버리지, 최초/최종 관측일, 적격 상태와 단계별 제외 사유를 기록합니다.
- 14일 staleness, no-leading-fill alignment, USD base-currency 정책을 응답에 함께 명시합니다.

## 제외 사유

- fetch: `no_price_data`
- minimum history: `insufficient_history`
- liveness: `stale_price`
- currency conversion: `fx_unavailable`
- sanitization: `invalid_price`
- forecast: `forecast_output_missing`
- alignment: `alignment_missing`

## 검증

- 일부 ticker만 최소 거래일/liveness 조건을 통과하는 성공 경로
- 전체 ticker가 데이터 부족으로 탈락하는 오류 경로
- optimizer 최종 응답까지 진단 payload 보존
