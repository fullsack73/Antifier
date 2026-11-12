# 전략 백테스트의 사용자 모델 조합 선택

- 일시: 2026-11-12 21:04 KST
- 에이전트: Codex
- 요청: 고정 GMV/MPT/overlay 체크박스를 Optimizer와 같은 사용자 선택으로 전환

## 변경

비교 항목을 추가·제거하고 각 항목에서 최적화 방식과 예측 방식을 선택한다.
최적화는 GMV, MPT, Black-Litterman, 기존 실험 GMV+예측 overlay를 지원한다.
예측은 Optimizer와 같은 LIGHTWEIGHT, ARIMA_TRANSFORMER, TRANSFORMER를 지원하며
GMV는 RISK_ONLY로 정규화하고 화면에서도 예측 선택을 비활성화한다.
기본 화면은 GMV 한 항목이며 고정된 세 항목을 강제하지 않는다.

- `strategy_configs`로 1~10개의 서로 다른 조합을 검증하고 stable 조합 ID를 생성한다.
- 같은 origin의 동일 예측 방식은 한 번만 계산해 MPT/BL/overlay가 공유한다.
- 예상 작업량도 서로 다른 예측 방식 개수로 계산한다.
- 기존 production Transformer 및 ARIMA+Transformer의 버전·입력 hash·horizon 캐시를 재사용한다.
- 경량 예측의 기간 단순수익률은 연 로그수익률로 통일하고 MPT/BL 입력에서 연 단순수익률로 변환한다.
- BL은 기존 backtest와 같은 동일비중 시장 prior, delta 2.5, tau .05를 사용한다.
  최신 시가총액을 과거에 소급하지 않으며 화면과 결과에 가정을 명시한다.
- 결과 이름은 저장된 설정에서 생성하고 조합별 예측/불확실성/대체 사유를 표시·보존한다.
- 기존 `strategies` 요청과 고정 세 전략의 저장 결과를 계속 지원한다.
- production optimizer 기본값이나 기존 Optimizer 화면의 계산 규칙은 바꾸지 않았다.

## 검증

- Backend focused: 31 passed (1.17s).
- Frontend focused: 5 passed (1.64s).
- 사용자 선택 payload, GMV forecast 비활성화, 조합별 저장 이름·예측 구분,
  잘못된/중복 조합 거부, 예측 공유 횟수, BL posterior 실제 계산,
  경량 수익률 단위 변환, GMV 단독 예측 미실행을 검증했다.
- 기존 과거 입력 차단/현금·비용·낙폭 검산 테스트도 통과했다.
- 브라우저에서 두 항목 구성 후 BL+Transformer 선택 및 설명 표시를 확인했다.
  이 확인은 화면 동작이며 Yahoo 실데이터 모델 성과 실행이 아니다.
- `git diff --check`: 통과.
- 최종 전체 검증 완료: backend 566 passed (369.59s), frontend 39 passed, lint/build exit 0. 결과 파일:
  `logs/strategy-selectors-20261112/verification.log`, `verification.status`, `verification-checks.json`.

## 한계와 운영

- 사용자 서버는 재시작하지 않았으며 새 API 계산에는 백엔드 재시작이 필요하다.
- 확인용 5179 서버는 종료했다. 기존 5000 포트 서버는 변경하지 않았다.
- 과거 BL의 동일비중 시장 가정은 현재 시가총액을 사용하는 live BL과 구분한다.
- 실제 대규모 ML 비교·장시간 부하는 실행하지 않았다. 투자 성과 개선을 주장하지 않는다.
- 커밋·푸시는 하지 않았다.
