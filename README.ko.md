<div align="center">

# 📊 Antifier

**지능형 금융 분석 및 포트폴리오 최적화 플랫폼**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 16+](https://img.shields.io/badge/node-16+-green.svg)](https://nodejs.org/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://reactjs.org/)
[![Flask](https://img.shields.io/badge/flask-3.1+-000000.svg)](https://flask.palletsprojects.com/)

[주요 기능](#-주요-기능) • [설치](#-설치) • [사용법](#-사용법) • [문서](#-문서) • [기여하기](#-기여하기)

---

**언어:** [🇺🇸 English](README.md) | 🇰🇷 한국어

</div>

---

## 🎯 개요 (Overview)

**Antifier**는 주식 리서치, 예측 모델링, 재무제표 검토, 종목 스크리닝, 헤지 분석, 포트폴리오 최적화, 벤치마킹, 리밸런싱을 한 곳에서 수행할 수 있는 로컬 React + Flask 금융 분석 웹 애플리케이션입니다.

"Antifier"라는 이름은 소액 개인 투자자를 뜻하는 한국어 표현인 "개미"에서 유래했습니다. Antifier는 투자 자문이나 수익 보장을 제공하는 서비스가 아니라 분석을 보조하는 도구입니다.

### 왜 Antifier인가요?

- **🔄 연결된 분석 흐름**: 가격 차트와 예측부터 재무 지표, 스크리닝, 헤지 확인, 포트폴리오 최적화, 벤치마킹, 리밸런싱까지 한 앱에서 처리
- **🤖 예측 기반 모델링**: 작업 흐름에 맞게 LSTM, LightGBM, ARIMA, ARIMA + Transformer, Transformer, 경량 예측 경로를 선택
- **📊 재무 맥락 제공**: 밸류에이션, 수익성, 성장성, 안정성, 위험 지표와 섹터/산업 벤치마크를 함께 확인
- **🎯 포트폴리오 전체 흐름 지원**: MPT 또는 Black-Litterman으로 최적화하고, 포트폴리오 JSON을 내보낸 뒤 S&P 500/무위험 자산과 비교하고 리밸런싱 주문으로 변환
- **🌐 로컬 이중언어 앱**: 영어/한국어 UI, `/api` 프록시, 설치/빌드 도구를 갖춘 React/Vite 프론트엔드와 Flask API를 로컬에서 실행

---

## ✨ 주요 기능 (Features)

### 📊 주식 분석 및 예측
- 날짜 범위를 설정할 수 있는 단일 종목 주가 차트
- LSTM, LightGBM, ARIMA, ARIMA + Transformer, Transformer 기반 회귀/예측 모델 선택
- 예측 기간과 범위를 표시하는 미래 가격 예측 차트
- 원 통화와 표시 통화가 다를 때 가격 통화 메타데이터 표시

### 📋 재무제표 및 종목 스크리닝
- 기업 요약, 시가총액, 통화 정보, 지표 점수, 규칙 기반 분석 신호를 제공하는 재무 대시보드
- 밸류에이션, 수익성, 성장성, 안정성, 위험 지표와 산업/섹터 벤치마크 비교
- Finviz 섹터/산업 밸류에이션 벤치마크와 yfinance 대표 peer 기반 보완 벤치마크
- S&P 500, Dow Jones, 업로드한 CSV 종목 universe를 대상으로 한 다중 재무 필터 스크리닝과 CSV 내보내기

### 💼 포트폴리오 최적화
- production 기본값인 Ledoit-Wolf 글로벌 최소분산과 명시적으로 선택하는 MPT 및 Black-Litterman
- 예측 기대수익률을 활용한 현대 포트폴리오 이론(MPT) 및 Black-Litterman 최적화
- 경량 예측, ARIMA + Transformer, 단독 Transformer forecast 전략 선택
- 종목 cap, L2 분산화, 최소 보유 비중, turnover, 종목별 override, 섹터·산업·국가 노출 범위 고급 설정
- solver 실행 전 feasibility 검사와 구조화된 제약 오류를 제공하며, 최신 yfinance 분류를 과거 point-in-time metadata처럼 표시하지 않음
- 장시간 최적화 작업의 진행률 스트리밍, 포트폴리오 JSON 다운로드, 수익률/위험/Sharpe, 리스크 기여도, 집중도, 공분산, metadata coverage, 제약 slack, weight 테이블 제공
- 투자 예산을 주식 수량으로 변환하고 전체 또는 종목별 fractional share 설정 지원

### 📈 포트폴리오 벤치마킹 및 리밸런싱
- 포트폴리오 JSON 업로드 후 S&P 500과 설정 가능한 무위험 자산 대비 성과 비교
- 현재 보유 종목, 현금 주입, 목표 자산 universe, turnover 제어를 기준으로 리밸런싱 주문 계산
- 포트폴리오 입력 로컬 저장/불러오기, 목표 보유 종목 CSV 내보내기, 포트폴리오 JSON 다운로드, 리밸런싱 결과 저장/출력
- 선택한 기간의 두 종목 상관관계와 회귀를 활용한 헤지 분석

---

## 📋 필수 요구 사항 (Prerequisites)

Antifier를 설치하기 전에 시스템에 다음 항목들이 설치되어 있는지 확인해 주세요.

- **Python 3.8+**: 백엔드 처리 및 설치 프로그램 실행에 필요
  - [python.org](https://www.python.org/downloads/)에서 다운로드
  - 확인: `python --version` 또는 `python3 --version`

- **Node.js 16+**: 프론트엔드 개발 서버에 필요
  - [nodejs.org](https://nodejs.org/)에서 다운로드
  - 확인: `node --version`

이 항목들은 원클릭 설치 및 수동 설치 방법 모두에 필요합니다.

---

## 🚀 설치 (Installation)

### 방법 1: 원클릭 설치 (권장)

[Releases](https://github.com/fullsack73/Antifier/releases) 페이지에서 운영체제에 맞는 독립 실행형 설치 프로그램을 다운로드하세요:

**macOS:**
```bash
chmod +x antifier-installer-macos
./antifier-installer-macos
```

**Windows:**
```cmd
antifier-installer-windows.exe
```

**Linux:**
```bash
chmod +x antifier-installer-linux
./antifier-installer-linux
```

설치 프로그램은 자동으로 다음 작업을 수행합니다:
- Python 가상 환경 설정
- 모든 의존성 패키지 설치
- 애플리케이션 설정
- 웹앱 실행

### 방법 2: 수동 설치

**사전 준비:**
- Python 3.8 이상
- Node.js 16 이상
- npm 또는 yarn

**설치 단계:**

1. **저장소 복제(Clone):**
```bash
git clone https://github.com/fullsack73/Antifier.git
cd antifier
```

2. **Python 환경 설정:**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows의 경우: .venv\Scripts\activate
pip install -r requirements-pypi.txt
```

3. **프론트엔드 의존성 설치:**
```bash
npm install
```

4. **애플리케이션 실행:**

**터미널 1 - 백엔드:**
```bash
python src/backend/app.py
```

**터미널 2 - 프론트엔드:**
```bash
npm run dev
```

5. **앱 접속:**
브라우저를 열고 `http://localhost:5173`으로 접속하세요.

---

## 📖 사용법 (Usage)

### 빠른 시작 (Quick Start)

1. **종목 선택 (Select Stock Ticker)**: 주식 심볼 입력 (예: AAPL, MSFT, GOOGL)
2. **날짜 범위 선택 (Choose Date Range)**: 분석할 과거 데이터 기간 선택
3. **분석 보기 (View Analysis)**: 차트, 추세, 예측 데이터 탐색
4. **포트폴리오 최적화 (Optimize Portfolio)**: 포트폴리오에 주식 추가 및 최적화 실행
5. **결과 검토 (Review Results)**: 효율적 투자선 및 최적 배분 비중 분석

---

## 🏗️ 아키텍처 (Architecture)

### 기술 스택 (Technology Stack)

**프론트엔드 (Frontend):**
- React 19 (Hooks 사용)
- Vite (빌드 도구)
- Plotly.js (인터랙티브 차트)
- i18next (국제화)
- Axios (API 통신)

**백엔드 (Backend):**
- Flask 3.1+ (Python 웹 프레임워크)
- 머신러닝: LightGBM/LSTM 주가 회귀, ARIMA + Transformer 수익률 예측, 경량 통계 예측 fallback
- PyPortfolioOpt (현대 포트폴리오 이론 최적화)
- Pandas (데이터 조작)
- NumPy/SciPy (수치 계산)
- yfinance (주식 데이터 수집)
- finvizfinance (Finviz 섹터/산업 밸류에이션 벤치마크)

**빌드 및 배포 (Build & Distribution):**
- PyInstaller (실행 파일 패키징)
- GitHub Actions (CI/CD)
- 멀티 플랫폼 지원 (macOS, Windows, Linux)

### 프로젝트 구조

```
antifier/
├── src/
│   ├── backend/          # Flask API 및 ML 모델
│   │   ├── app.py        # 메인 Flask 애플리케이션
│   │   ├── forecast_models.py
│   │   ├── portfolio_optimization.py
│   │   └── stock_screener.py
│   └── frontend/         # React 컴포넌트
│       ├── App.jsx       # 메인 앱 컴포넌트
│       ├── Optimizer.jsx
│       ├── StockChart.jsx
│       └── locales/      # i18n 번역 파일
├── tools/                # 빌드 및 설치 스크립트
│   ├── installer.py      # 독립 실행형 설치 프로그램
│   └── build-*.sh/bat    # 플랫폼별 빌드 스크립트
├── tests/                # 테스트 모음
├── .github/workflows/    # CI/CD 파이프라인
└── requirements-pypi.txt # Python 의존성 목록
```

---

## 📚 문서 (Documentation)

- **에이전트 작업 규칙**: [AGENTS.md](AGENTS.md) 참고
- **폴더 아키텍처**: [docs/01-folder-architecture.md](docs/01-folder-architecture.md) 참고
- **기술 스펙**: [docs/02-specs.md](docs/02-specs.md) 참고
- **제품 기획안**: [docs/03-product-plan.md](docs/03-product-plan.md) 참고
- **TODO 인덱스**: [docs/todo/00-todo-list.md](docs/todo/00-todo-list.md) 참고
- **작업 기록**: [docs/reports/](docs/reports/) 참고
- **빌드 가이드**: [tools/BUILD.md](tools/BUILD.md) 참고

---

## 🤝 기여하기 (Contributing)

모든 형태의 기여를 환영합니다! 다음과 같은 방법으로 참여할 수 있습니다:

1. **저장소 포크 (Fork)**
2. **기능 브랜치 생성**: `git checkout -b feature/amazing-feature`
3. **변경 사항 커밋**: `git commit -m 'Add amazing feature'`
4. **브랜치에 푸시**: `git push origin feature/amazing-feature`
5. **Pull Request 생성**

### 개발 가이드라인

- 기존 코드 스타일 및 규칙 준수
- 새로운 기능에 대한 테스트 코드 작성
- 필요 시 문서 업데이트
- PR 제출 전 모든 테스트 통과 확인

---

## 📄 라이선스 (License)

이 프로젝트는 **크리에이티브 커먼즈 저작자표시-비영리 4.0 국제 라이선스 (CC BY-NC 4.0)** 하에 배포됩니다.

### 이용 가능 권한:

- **공유 (Share)** — 어떤 매체나 형식으로든 자료를 복제 및 재배포할 수 있습니다.
- **변경 (Adapt)** — 자료를 리믹스, 변형 및 2차 저작물을 작성할 수 있습니다.

### 다음 조건을 준수해야 합니다:

- **저작자 표시 (Attribution)** — 적절한 출처를 표시하고, 라이선스 링크를 제공하며, 변경이 있었는지 여부를 명시해야 합니다.
- **비영리 (NonCommercial)** — 이 자료를 영리 목적으로 이용할 수 없습니다.
- **추가 제한 금지 (No additional restrictions)** — 이용허락자가 허용한 행위를 법적 조건이나 기술적 조치를 통해 제한해서는 안 됩니다.

### 중요 유의사항:

- 이 소프트웨어는 **개인적, 교육적, 연구적 목적**으로만 제공됩니다.
- 소프트웨어 판매, 상업적 서비스에서의 사용, 배포를 통한 수익 창출을 포함한 **상업적 이용은 엄격히 금지**되며, 별도의 서면 허가가 필요합니다.
- 제3자 데이터 제공업체(특히 Yahoo Finance)의 서비스 약관을 준수해야 합니다.

전체 라이선스 전문은 [LICENSE](LICENSE) 파일을 확인하거나 다음 링크를 방문하세요:
https://creativecommons.org/licenses/by-nc/4.0/

---

## 🙏 감사의 말 (Acknowledgments)

- **데이터 소스**: [Yahoo Finance](https://finance.yahoo.com/)에서 금융 데이터 제공
- **머신러닝**: [LightGBM](https://github.com/microsoft/LightGBM), ARIMA, Transformer 모델, 경량 통계 예측 활용
- **최적화**: 현대 포트폴리오 이론 구현을 위한 [PyPortfolioOpt](https://pypi.org/project/pyportfolioopt/)
- **시각화**: [Plotly.js](https://plotly.com/javascript/)로 차트 렌더링

---

## ⚠️ 면책 조항 (Disclaimer)

**이 소프트웨어는 교육 및 정보 제공 목적으로만 사용됩니다.**

Antifier는 등록된 투자 자문사가 아니며, 금융 자문을 제공하지 않습니다. 이 소프트웨어가 생성하는 분석, 예측 및 추천은 금융, 투자 또는 트레이딩 조언으로 간주되어서는 안 됩니다.

- 과거의 성과가 미래의 결과를 보장하지 않습니다.
- 모든 투자 결정에는 손실 위험이 따릅니다.
- 항상 독자적인 조사를 수행하고 자격을 갖춘 금융 전문가와 상담하세요.
- 개발자와 기여자는 어떠한 금융 손실에 대해서도 책임을 지지 않습니다.

**사용에 따른 위험은 사용자 본인이 감수해야 합니다.**
