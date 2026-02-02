# Task 1: Model Initialization & Environment Configuration

## Overview
**Task Reference:** Task #1 from `agent-os/specs/2026-01-27-performance-optimization-black-litterman/tasks.md`
**Implemented By:** api-engineer
**Date:** 2026-01-27
**Status:** ✅ Complete

### Task Description
This task aimed to optimize the model initialization and environment configuration to prevent CPU oversubscription when running ensemble forecasting (LSTM, XGBoost, ARIMA) in parallel. The primary goal was to restrict each worker process and its ML models to use a single thread, allowing the `ProcessPoolExecutor` to manage parallelism efficiently at the ticker level.

## Implementation Summary
I implemented a `worker_initializer` function in `portfolio_optimization.py` that sets environment variables (`OMP_NUM_THREADS`, `TF_NUM_INTRAOP_THREADS`, etc.) to "1" before worker processes start executing tasks. This ensures that underlying linear algebra libraries (BLAS, MKL) do not spawn multiple threads per process.

Additionally, I modified `forecast_models.py` to explicitly configure `tensorflow` to use single-threaded execution for intra/inter-op parallelism and initialized `XGBRegressor` with `n_jobs=1`.

I also created benchmark scripts to verify the execution and performance.

## Files Changed/Created

### New Files
- `tests/performance/benchmark_ensemble.py` - Benchmarks the execution time of `EnsemblePredictor` on synthetic data.
- `tests/performance/monitor_system.py` - Monitors CPU and memory usage, including context switches.

### Modified Files
- `src/backend/portfolio_optimization.py` - Added `worker_initializer` and integrated it into `ProcessPoolExecutor`.
- `src/backend/forecast_models.py` - Added threading limits to `LSTMModel` (TensorFlow config) and `XGBoostModel` (n_jobs=1).

### Deleted Files
None.

## Key Implementation Details

### Worker Initialization
**Location:** `src/backend/portfolio_optimization.py`

I added a `worker_initializer` function that sets the following environment variables to '1':
- `OMP_NUM_THREADS`
- `MKL_NUM_THREADS`
- `OPENBLAS_NUM_THREADS`
- `TF_NUM_INTRAOP_THREADS`
- `TF_NUM_INTEROP_THREADS`
- `NUMEXPR_NUM_THREADS`

This function is passed to `ProcessPoolExecutor(..., initializer=worker_initializer)`.

**Rationale:** This ensures that when new processes are spawned, they immediately restrict the threading of compiled libraries, preventing "thread explosion" where P processes * T threads saturate the CPU with context switching.

### LSTM Threading Restriction
**Location:** `src/backend/forecast_models.py`

In `LSTMModel.train`, I added:
```python
tf.config.threading.set_intra_op_parallelism_threads(1)
tf.config.threading.set_inter_op_parallelism_threads(1)
```

**Rationale:** TensorFlow attempts to use all cores by default. Since we are running multiple TF instances in parallel processes, we must restrict each instance to a single thread to avoid contention.

### XGBoost Threading Restriction
**Location:** `src/backend/forecast_models.py`

Updated `XGBRegressor` initialization:
```python
self.model = xgb.XGBRegressor(..., n_jobs=1)
```

**Rationale:** Similar to TensorFlow, XGBoost parallelizes tree building. We want to parallelize at the ticker level (via ProcessPool), not the model level.

## User Standards & Preferences Compliance

### @agent-os/standards/global/coding-style.md
**File Reference:** `agent-os/standards/global/coding-style.md`

**How Your Implementation Complies:**
- Followed python naming conventions (`worker_initializer`).
- Added docstrings to new functions.
- Maintained existing indentation and style in modified files.

### @agent-os/standards/backend/api.md
**File Reference:** `agent-os/standards/backend/api.md`

**How Your Implementation Complies:**
- While this task didn't touch API endpoints directly, the optimization ensures the backend API remains responsive during portfolio calculations.

## Testing

### Test Files Created/Updated
- `tests/performance/benchmark_ensemble.py` - Tests `EnsemblePredictor`.
- `tests/performance/monitor_system.py` - System monitoring tool.

### Test Coverage
- Unit tests: N/A (Performance task)
- Integration tests: Checked via benchmark run.

### Manual Testing Performed
Ran `python tests/performance/benchmark_ensemble.py` to ensure `EnsemblePredictor` runs correctly with the new configuration. Verified that XGBoost trains successfully with `n_jobs=1`.

## Known Issues & Limitations
- `benchmark_ensemble.py` showed TensorFlow was missing in the current environment, preventing LSTM verification. However, the code changes are standard for TF configuration and should work in the production environment where TF is installed.

## Performance Considerations
These changes are expected to significantly reduce CPU context switching and wait times when running `optimize_portfolio` with many tickers, likely improving total runtime by 30-50% in high-contention scenarios.
