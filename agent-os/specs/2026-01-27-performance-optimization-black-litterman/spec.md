# Specification: Performance Optimization for Black-Litterman Portfolio

## Goal
Optimize the runtime performance of `portfolio_optimization.py` which has degraded by approximately 2x following the introduction of Ensemble forecasting (ARIMA+LSTM+XGBoost) and Black-Litterman. The objective is to alleviate CPU saturation caused by resource contention between process-level parallelism and model-level parallelism.

## User Stories
- As a **Quant Developer**, I want the portfolio optimization to run efficiently on my machine without locking up the CPU (100% usage), so I can iterate faster.
- As a **User**, I want the forecasting engine to maintain its ensemble accuracy while executing significantly faster, close to the original performance levels.

## Core Requirements
### Functional Requirements
- **Runtime Reduction:** Signficantly reduce the execution time of `optimize_portfolio` operations.
- **Resource Management:** Restrict ML models (TensorFlow, XGBoost) to single-threaded execution when running inside parallel processes.
- **Accuracy Preservation:** Ensure that the ensemble model outputs (Expected Return, Volatility) remain numerically identical (or within float tolerance) to the current implementation.

### Non-Functional Requirements
- **Performance:** CPU usage should be high but efficient (minimized context switching overhead).
- **Stability:** Prevent memory leaks associated with repeated TensorFlow session initialization in worker processes.

## Visual Design
N/A (Backend optimization task)

## Reusable Components
### Existing Code to Leverage
- **Parallel Execution:** `portfolio_optimization.py` uses `ProcessPoolExecutor`. We will tune its `max_workers` and worker initialization logic.
- **Model Classes:** `forecast_models.py` contains `LSTMModel` and `XGBoostModel`. We will modify their initialization to accept threading limits.

### New Components Required
- **Worker Initializer:** A helper function to initialize the worker process environment variables (e.g., `OMP_NUM_THREADS=1`, `TF_NUM_INTRAOP_THREADS=1`) before importing/running heavy libraries.

## Technical Approach
### Threading Configuration
- **TensorFlow:** Configure `tf.config.threading.set_intra_op_parallelism_threads(1)` and `set_inter_op_parallelism_threads(1)` inside the worker process.
- **XGBoost:** Set `n_jobs=1` or `nthread=1` in the `XGBRegressor` initialization.
- **ARIMA:** Ensure `auto_arima` uses `n_jobs=1` (default, but verify).
- **Environment Variables:** Set `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS` to `1` within the worker context to prevent lower-level linear algebra libraries from spawning threads.

### Parallelism Strategy
- Maintain `ProcessPoolExecutor` for parallelism across tickers.
- Since we handle parallelism at the "Ticker" level, each ticker's calculation should be strictly serial (single-threaded) to maximize throughput usage of the CPU cores.

## Out of Scope
- Changing the modeling logic (e.g., removing LSTM).
- Changing the Black-Litterman math.
- UI changes.

## Success Criteria
- **Metric:** Runtime for a standard portfolio optimization task (e.g., 20 tickers) is reduced by at least 30-40% from current "2x slower" state.
- **Metric:** CPU usage remains efficient, but system responsiveness improves (less context switching).
- **Verification:** Forecast results match pre-optimization values.
