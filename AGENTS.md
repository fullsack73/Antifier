# Agent Working Agreement

이 파일은 Codex, Copilot 등 이 저장소에서 작업하는 개발 에이전트와 사람이 공유하는 작업 규칙입니다.
Antifier의 문서가 매 작업의 실행 컨텍스트가 되도록 유지하는 것이 목적입니다.

## 반드시 읽기

작업을 시작하기 전에 아래 문서를 먼저 확인합니다.

- `docs/01-folder-architecture.md`
- `docs/02-specs.md`
- `docs/03-product-plan.md`
- `docs/todo/00-todo-list.md`

작업이 기존 `agent-os/` 스펙과 직접 연결되어 있으면 관련 `agent-os/specs/*` 문서도 함께 확인합니다. 다만 현재 저장소의 우선 문서 체계는 루트의 `AGENTS.md`와 `docs/`입니다.

## 작업 시작 체크리스트

- 필수 문서를 읽고 현재 요청과 충돌하는 규칙이 없는지 확인했는가
- `docs/todo/00-todo-list.md`에서 관련 후속 작업을 확인했는가
- 변경이 Antifier의 핵심 범위인 금융 분석, 예측, 포트폴리오 최적화, 설치/배포 지원을 벗어나지 않는가
- 프론트엔드 변경은 `src/frontend`의 컴포넌트 중심 구조와 기존 CSS/i18n 패턴을 따르는가
- 백엔드 변경은 `src/backend/app.py`의 API 오케스트레이션과 도메인 모듈 분리 방식을 지키는가
- API 호출은 프론트엔드에서 `src/frontend/apiClient.js`의 `apiUrl`을 우선 사용하는가
- 투자 판단을 대신하는 표현이 아니라 분석 보조 도구라는 제품 범위를 유지하는가
- 외부 금융 데이터 호출 실패, 빈 데이터, 비정상 입력에 대한 방어 로직을 고려했는가

## 코드 변경 규칙

- React 코드는 기존 JavaScript/JSX 스타일을 유지하고 새 TypeScript 구조를 도입하지 않습니다.
- 프론트엔드 API 경로는 `/api` prefix를 기본으로 하며, Vite proxy와 `VITE_API_BASE_URL` 양쪽에서 동작해야 합니다.
- 장시간 실행되는 포트폴리오 최적화 작업은 기존 progress stream 패턴을 해치지 않습니다.
- 백엔드 입력값은 ticker/date/number별 검증 함수를 재사용하거나 같은 수준의 검증을 추가합니다.
- yfinance, finvizfinance 같은 외부 데이터 의존성은 실패 가능성을 전제로 예외와 빈 응답을 처리합니다.
- ML/최적화 변경은 계산 비용, 메모리 사용량, native thread 제한, CI 의존성 범위를 함께 고려합니다.
- 통화 변환, 수익률 연율화, 포트폴리오 weight 계산은 기존 단위와 의미를 명확히 유지합니다.
- 한국어/영어 UI 문구를 추가하면 `src/frontend/locales/en/translation.json`와 `src/frontend/locales/ko/translation.json`를 함께 갱신합니다.
- 새 기능과 버그 수정은 가능한 범위에서 `tests/`에 회귀 테스트를 추가합니다.

## 문서 업데이트 규칙

- 폴더 책임, 기술 스택, API 규칙, 제품 범위가 바뀌면 `docs/01`, `docs/02`, `docs/03` 중 해당 문서를 함께 갱신합니다.
- 코드와 문서가 충돌하면 먼저 문서를 현재 의도에 맞게 정리한 뒤 구현합니다.
- 중대한 변경, 아키텍처 결정, 문서 체계 변경은 `docs/reports/`에 작업 기록을 남깁니다.
- 작업 기록 파일명은 `yymmdd-HHMM-NN-작업키워드.md` 형식을 사용합니다.
- 지금 처리하지 못하지만 추후 반드시 진행해야 하는 일은 `docs/todo/`에 TODO 문서를 추가합니다.
- TODO를 추가하면 `docs/todo/00-todo-list.md`에도 한 줄 요약을 함께 추가합니다.
- TODO를 완료하면 해당 TODO 파일을 삭제하고 `docs/reports/`에 완료 기록을 남긴 뒤 `00-todo-list.md`에서도 제거합니다.
- 요청과 관련된 TODO가 있으면 해당 TODO 문서를 읽고, 현재 요청에 같이 반영할지 사용자에게 먼저 알립니다.

## 검증 기준

- 프론트엔드: `npm run lint`, `npm test`, `npm run build`
- 백엔드: `PYTHONPATH=src/backend python -m pytest tests`
- 설치/배포 변경: 관련 `tools/build-*.sh`, `tools/installer.py`, `.github/workflows/build-installer.yml` 흐름 확인
- 문서만 변경한 경우에는 링크, 파일명, TODO 인덱스, 예시/플레이스홀더 잔존 여부를 확인합니다.

## 참고 우선순위

1. `AGENTS.md`와 `docs/`
2. 현재 코드와 테스트
3. `agent-os/product` 및 관련 `agent-os/specs`
4. README와 빌드 문서
5. 과거 작업 기록과 TODO
