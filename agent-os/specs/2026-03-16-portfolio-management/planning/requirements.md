# Spec Requirements: portfolio-management

## Initial Description
포트폴리오 관리 기능을 새로 만들고 싶어.

구체적인 기능 사항은 다음과 같아:
- **입력**: 
  - 유저의 현재 포트폴리오 및 자산배분 상태가 기재된 `.json` 파일
  - (선택 사항) 새로 투자할 현금(Cash Injection) 금액
- **출력**:
  - 현재 포트폴리오와 조정 후 포트폴리오를 비교하는 2개의 파이 차트
  - **Sell List**: 현재 보유 자산에서 어떤 것을 얼마만큼 팔아야 하는지 나타내는 목록
  - **Buy List**: 매도한 금액 + 새로운 현금 투자액으로 어떤 것을 얼마만큼 사야 하는지 나타내는 목록

## Requirements Discussion

### First Round Questions

**Q1:** I assume the inputted `.json` file contains both the current holdings (e.g., tickers and quantities) and the target asset allocation weights. Is that correct, or should users define their target allocations interactively through the UI?
**Answer:** frontend ui를 통해 사용자가 자산 배분 현황을 입력하면 그게 .json로 변환되어서 조정 엔진으로 전달될거야

**Q2:** I assume we will use our existing `yfinance` integration to fetch real-time or most recent closing prices to accurately calculate the valuation of the current portfolio and the buy/sell lists. Is that correct?
**Answer:** 맞아 주가시계열 데이터는 yfinance를 사용해서 가져올거야

**Q3:** I'm thinking the buy and sell lists should provide quantities in exact fractional shares for mathematical precision. Should we output fractional shares, or should we round to whole shares (and if so, how do we handle leftover cash)?
**Answer:** 맞아 정확히 소수점 형태로 얼마나 팔고 사야하는지 제시되어야 해. left over 유동성이랑 fractional이 지원 안되는 경우에 관한 문제는 @[src/frontend/Optimizer.jsx]에서 똑같은 문제를 다루는 부분이 있으니 그걸 참고하면 돼

**Q4:** I assume we should use our existing `Plotly.js` charting library to render the two comparison pie charts (Current vs. Adjusted Portfolio). Is that correct?
**Answer:** 맞아

**Q5:** I'm assuming the rebalancing logic will simply calculate the differences between current and target allocations, applying the optional cash injection to minimize selling where possible. Is that correct, or do you have a specific rebalancing algorithm in mind?
**Answer:** 잘못 이해하고 있는 것 같은데 target allocation은 유저가 입력하는게 아니라 여기서 계산을 해줘야 해. 유저가 입력한 space, 또는 유저가 업로드한 csv파일을 space로 하고 최근 5년(혹은 유저가 지정한 기간)에 대하여 @[src/backend/portfolio_optimization.py]이 스크립트를 ML + Black-litterman(아니면 유저가 지정한 최적화 방법)으로 돌려서 타겟 포트폴리오를 뽑을거야. 이때, target return이랑 risk는 20, 15를 기본값으로 해서 샤프지수가 최대가 되는 지점을 찾을 떄 까지 알아서 조정하면서 포트폴리오 최적화를 돌릴거야(물론 ML + 최적화를 돌리는게 아니라 최적화만 반복해서 돌려야돼)

**Q6:** I assume the UI for this feature will involve an upload button for the `.json` file, an input field for the optional cash injection, and a dashboard displaying the pie charts alongside the buy/sell tables. Is that correct?
**Answer:** 맞아 니가 말한거랑 그거에 더해서 space 올릴 수 있는 upload 버튼이랑 최적화 방법, 기간등을 조절할 수 있는 설정창이 필요해. 그거도 @[src/frontend/Optimizer.jsx]에 구현되어 있으니까 참고하면 돼

**Q7:** Finally, are there any specific edge cases we need to handle (such as uninvested cash currently in the portfolio, transaction fees, or taxes), or are those explicitly out of scope for this feature?
**Answer:** 없어.

### Existing Code to Reference

**Similar Features Identified:**
- Feature: Fractional shares / Left-over liquidity handling & UI settings/upload buttons - Path: `src/frontend/Optimizer.jsx`
- Components to potentially reuse: Space upload button, optimization configuration settings panel
- Backend logic to reference: Target portfolio generation using ML + Black-litterman/optimization methods in `src/backend/portfolio_optimization.py`

### Follow-up Questions
No follow-ups needed.

## Visual Assets

### Files Provided:
No visual assets provided.

## Requirements Summary

### Functional Requirements
- Frontend UI to input current portfolio holdings, converted to JSON, and passed to backend.
- Option to input additional cash injection.
- Fetch asset stock prices using `yfinance`.
- Upload tool / field for target "space" (candidate assets), or uploading a CSV file to form the space over a given time period (default: 5 years).
- Configurations for optimization: selection of optimization method, historical period.
- Backend computes optimal target allocation using `src/backend/portfolio_optimization.py` (e.g., using ML + Black-Litterman or selected method) iteratively adjusting target return and risk (default 20, 15) to maximize Sharpe Ratio.
- Return explicit exact fractional shares for "Buy" and "Sell" lists.
- Display two Plotly.js pie charts comparing current vs. optimized portfolio allocation.

### Reusability Opportunities
- Handling of exact fractional shares constraints and leftover liquidity logic, mirroring implementations in `src/frontend/Optimizer.jsx`.
- Using UI components (upload buttons, calculation settings panels) present in `src/frontend/Optimizer.jsx`.
- Existing backend functionality from `src/backend/portfolio_optimization.py` for portfolio generation.

### Scope Boundaries
**In Scope:**
- Portfolio composition UI -> JSON payload.
- Space management (UI/upload) and optimization configuration.
- Repeated backend optimization calculations to extract an optimal max-Sharpe portfolio.
- Accurate fractional stock buy/sell difference lists.
- Pre vs Post visualization pie charts.

**Out of Scope:**
- Edge cases specifically handling uninvested cash, transaction fees, and taxes explicitly mentioned as not necessary.

### Technical Considerations
- Plotly.js for pie charts.
- `yfinance` API calls in backend.
- Iterative loop logic within the optimizer to automatically adjust target limits until max Sharpe Ratio is identified on the generated target space.
