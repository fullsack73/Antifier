# TODO - Hedge Analysis 리팩터링

- 등록 일시: 2026-07-03 00:16 (Asia/Seoul)
- 작성자: 사용자 요청
- 에이전트: Codex
- 진행 시점: Hedge Analysis 화면/API를 다음에 수정할 때

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- Hedge Analysis는 삭제하지 않고 유지하되, 단순 "hedge 여부" 판정 기능이 아니라 pairs/correlation/regression 분석 도구로 재정의합니다.
- 사용자가 두 종목의 관계를 탐색할 수 있게 하되, 투자 판단이나 hedge 성립을 단정하지 않는 분석 보조 표현으로 바꿉니다.

## 판단 근거

- `docs/03-product-plan.md`는 활동적인 트레이더의 핵심 흐름에 hedge 분석을 포함하고, 구현 완료 범위에도 hedge/pairs trading 분석을 명시합니다.
- `src/frontend/Hedge.jsx`, `src/frontend/Selector.jsx`, `/api/analyze-hedge`, `src/backend/hedge_analysis.py`가 이미 연결되어 있어 기능 자체는 독립 화면/API로 동작합니다.
- 현재 문제는 기능 가치 부족보다 `correlation < -0.5`를 `is_hedge`로 단정하는 계산/표현 방식, 기간 부족 방어, 실패 응답, 테스트 부재입니다.

## 요구사항

- 화면명과 문구를 "Hedge Relationship Analysis" 중심에서 "Pairs / Correlation Analysis" 성격으로 조정합니다.
- `is_hedge` Yes/No 카드는 제거하거나 "negative correlation signal"처럼 비단정적 지표로 대체합니다.
- 상관계수, p-value, 회귀 beta/alpha, R-squared, 관측치 수, 분석 기간을 응답과 UI에 명확히 표시합니다.
- 최소 공통 거래일 수를 정의하고, 부족하면 4xx 의미에 맞는 에러와 사용자 친화적인 메시지를 반환합니다.
- 두 ticker가 같거나, ticker/date 형식이 잘못되거나, 한쪽 데이터가 비어 있거나, 수익률 계산 후 공통 날짜가 부족한 경우를 방어합니다.
- yfinance 호출 실패와 `stock.info` 실패를 서버 traceback 없이 처리합니다.
- API는 `/api/analyze-hedge` 경로를 당분간 유지하되, 응답 필드는 새 의미에 맞게 문서화하고 프론트엔드와 테스트를 함께 갱신합니다.
- 영어/한국어 locale을 함께 갱신합니다.
- 투자 자문, 수익 보장, 자동 매매 지시처럼 읽히는 문구를 제거합니다.

## 작업 요약

- Backend: `src/backend/hedge_analysis.py`를 pairs/correlation/regression 분석 모듈로 정리하고, 입력/기간/데이터 부족 검증과 실패 응답을 보강합니다.
- API: `src/backend/app.py` endpoint에서 date 검증 실패와 외부 데이터 실패를 적절한 HTTP status로 반환합니다.
- Frontend: `src/frontend/Hedge.jsx` 결과 카드를 hedge Yes/No가 아닌 관계 분석 지표 중심으로 재구성합니다.
- Navigation/i18n: `src/frontend/Selector.jsx`와 locale 문구에서 기능명을 더 정확하게 조정합니다.
- Tests: backend 분석 함수/API 실패 케이스와 frontend 렌더링/API 호출 테스트를 추가합니다.
- Docs: 실제 응답 shape와 제품 설명이 바뀌면 `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md` 중 관련 문서를 갱신합니다.

## 선행조건

- 새 화면명이 "Pairs Analysis", "Correlation Analysis", "Relationship Analysis" 중 무엇인지 결정합니다.
- 기존 `/api/analyze-hedge` 응답을 외부에서 쓰는 사용자가 있는지 확인한 뒤, 호환 필드를 유지할지 결정합니다.

## 참고

- 관련 문서:
  - `docs/01-folder-architecture.md`
  - `docs/02-specs.md`
  - `docs/03-product-plan.md`
- 관련 코드:
  - `src/frontend/Hedge.jsx`
  - `src/frontend/Selector.jsx`
  - `src/frontend/locales/en/translation.json`
  - `src/frontend/locales/ko/translation.json`
  - `src/backend/app.py`
  - `src/backend/hedge_analysis.py`
- todo-list 한 줄 요약: Hedge Analysis를 삭제하지 않고 pairs/correlation/regression 분석 도구로 개편합니다.
