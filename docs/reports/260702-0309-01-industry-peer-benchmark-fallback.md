# 작업 기록 - 산업 대표 종목 benchmark fallback

- 일시: 2026-07-02 03:09 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 기능 개선/문서

## 요약

- 해외 종목이 Finviz 산업/섹터 benchmark에 매칭되지 않을 때 절대 기준으로 떨어지지 않도록 yfinance 기반 산업 대표 종목 평균 fallback을 추가했습니다.
- fallback 순서는 Finviz 산업 평균, Finviz 섹터 평균, 산업 대표 종목 평균, 섹터 대표 종목 평균입니다.

## 변경 범위

- `Consumer Electronics`, `Semiconductors`, `Auto Manufacturers` 등 주요 Yahoo industry 이름별 대표 ticker 10개 내외 dataset을 추가했습니다.
- 산업 대표 dataset의 ticker ratio를 yfinance로 조회해 산술 평균을 계산하고 24시간 캐시합니다.
- 대표 산업 dataset이 없는 경우 기존 섹터 대표 ticker 평균으로 fallback합니다.
- UI benchmark basis에 `industry_representative_average` 표시 문구를 추가했습니다.

## 주요 변경 파일

- `src/backend/financial_statement.py`
- `src/frontend/locales/en/translation.json`
- `src/frontend/locales/ko/translation.json`
- `tests/test_financial_statement.py`
- `docs/02-specs.md`
- `docs/03-product-plan.md`

## 검증

- `PYTHONPATH=src/backend ./.venv/bin/python -m pytest tests/test_financial_statement.py`
- `PYTHONPATH=src/backend ./.venv/bin/python -m pytest tests`
- `npm run lint`
- `npm test`
- `npm run build`
- live 확인: `005930.KS`, `000660.KS`가 절대 기준 fallback 대신 Finviz 산업 평균 benchmark를 사용

## 리스크/이슈

- 대표 ticker dataset은 공식 산업 평균이 아니라 산업 대형주 기반 근사치입니다.
- 신규 산업명이 들어오면 dataset에 산업 대표 ticker를 추가해야 더 정확한 fallback을 제공합니다.

## 다음 작업

- 실제 사용자 분석 종목에서 자주 등장하는 해외 industry 이름을 관찰해 dataset coverage를 확장합니다.
