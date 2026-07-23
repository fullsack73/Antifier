# TODO List

`docs/todo`에 있는 후속 작업을 한 줄씩 요약합니다. 작업 시작 전 이 파일을 먼저 확인하고, 관련 항목이 있으면 해당 TODO 문서를 함께 읽습니다.

- `portfolio-alpha-v2-research.md`: local SEC PIT fundamentals and joint-model diagnostics are complete, but the factor candidate failed; acquire sector metadata and a survivorship-safe historical universe before freezing any candidate.
- `portfolio-forecast-model-redesign.md`: pooled relative-return ridge is promising on a static-DOW diagnostic but fails Holm-adjusted promotion; do not tune Transformer until a promotion-safe universe confirms the signal.
- `portfolio-risk-model-research.md`: robust and OOS covariance-ensemble candidates failed frozen/statistical gates; covariance forecast/stress diagnostics are ready, so keep Ledoit-Wolf and do not run new validation without a fresh 95%-significant candidate.
- `portfolio-optimizer-quant-standard.md`: actual PIT data and 95% signal bootstrap are implemented; historical constituent membership, sector metadata, immutable splits, and a statistically significant frozen candidate remain.
