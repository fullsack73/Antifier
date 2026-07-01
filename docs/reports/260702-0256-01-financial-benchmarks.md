# 작업 기록 - 재무 benchmark 소스 개선

- 일시: 2026-07-02 02:56 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 기능 개선/문서

## 요약

- Financial Statement 대시보드의 업종/섹터 평균 비교 소스를 yfinance screener 평균에서 Finviz group valuation benchmark 우선 구조로 변경했습니다.
- Finviz 산업 평균을 먼저 사용하고, 없으면 Finviz 섹터 평균, 그래도 없으면 yfinance로 섹터 대표 대형주 평균을 계산합니다.

## 변경 범위

- `finvizfinance.group.valuation.Valuation`의 `Industry`/`Sector` valuation table을 1차 benchmark 소스로 사용합니다.
- benchmark table은 24시간 in-memory cache를 적용해 반복 요청 비용을 줄였습니다.
- Finviz benchmark가 없을 때는 섹터별 대표 대형주 10개 내외의 yfinance valuation ratio 단순 평균을 fallback으로 사용합니다.
- 국가 정보가 명확히 비미국인 종목은 미국 Finviz/대표 peer 평균을 붙이지 않고 절대 기준 평가로 남깁니다.
- UI에는 benchmark basis와 source를 함께 표시하도록 문구를 갱신했습니다.

## 주요 변경 파일

- `src/backend/financial_statement.py`
- `src/frontend/FinancialStatement.jsx`
- `src/frontend/locales/en/translation.json`
- `src/frontend/locales/ko/translation.json`
- `tests/test_financial_statement.py`
- `requirements-pypi.txt`
- `README.md`
- `README.ko.md`
- `docs/02-specs.md`
- `docs/03-product-plan.md`

## 검증

- `PYTHONPATH=src/backend ./.venv/bin/python -m pytest tests/test_financial_statement.py`
- `PYTHONPATH=src/backend ./.venv/bin/python -m pytest tests`
- `npm run lint`
- `npm test`
- `npm run build`
- live Finviz benchmark 확인: `Software - Infrastructure` 산업 평균 `P/E`, `Fwd P/E`, `P/B`, `P/S`, `PEG` 반환

## 리스크/이슈

- Finviz group table은 Finviz 웹 페이지 구조에 의존합니다. 실패 시 yfinance 대표 peer 평균으로 fallback합니다.
- 대표 peer 평균은 정식 산업 평균이 아니라 섹터 대형주 기반 근사치입니다.

## 다음 작업

- 필요하면 해외 시장별 benchmark 데이터 소스를 별도로 검토합니다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
