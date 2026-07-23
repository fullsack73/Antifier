# SEC PIT / Historical Universe Foundation

- 작업 일시: 2026-07-23 21:33 (KST)
- 작성자: Codex
- 상태: 코드·fixture 검증 완료, 실제 데이터 수집 대기

## 목적

Transformer 구조나 hyperparameter 탐색 전에 fundamental availability와 universe membership의 미래정보/생존편향을 제거합니다.

## 변경

- SEC companyfacts/submissions API client와 로컬 JSON cache를 추가했습니다.
- SEC filing date를 최초 사용 가능일로 사용합니다.
- quality, profitability, valuation, liquidity, filing-date market cap을 annual filing 단위로 생성합니다.
- 이후 제출된 10-K/A 정정공시가 이전 filing-date row를 수정하지 않도록 accession/filing-date 조건을 적용했습니다.
- `effective_date`, `ticker`, `in_universe` event 기반 universe manifest를 추가했습니다.
- signal date 이후의 편입/제외 event를 사용하지 않습니다.
- pooled cross-sectional feature 표준화, target, prediction을 각 signal date의 active universe로 제한했습니다.
- manifest와 factor output에 provenance와 SHA-256을 기록하는 CLI를 추가했습니다.

## 검증

- SEC/PIT 및 universe unit test 10개
- cross-sectional dynamic-universe 회귀 테스트
- 관련 선택 테스트 15개 통과
- 변경 Python module/CLI compile 통과

## 남은 조건

- 현재 환경에 연락처가 포함된 `SEC_USER_AGENT`가 없어 실제 SEC 다운로드는 실행하지 않았습니다.
- 실제 historical constituent manifest와 provenance source가 아직 없습니다.
- 따라서 factor-residual signal 성능과 optimizer default uplift는 아직 주장하지 않습니다.
- 실제 데이터 생성 후 fresh research split, candidate freeze, 새 validation, untouched locked holdout 순서로 검증합니다.
