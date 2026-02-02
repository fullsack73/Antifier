# Task Breakdown: Performance Optimization Black-Litterman

## Overview
Total Tasks: 3 Groups
Assigned roles: api-engineer, testing-engineer

## Task List

### Backend Optimization

#### Task Group 1: Model Initialization & Environment Configuration
**Assigned implementer:** api-engineer
**Dependencies:** None

- [x] 1.0 Optimize model initialization and threading
  - [x] 1.1 Write 2 performance benchmark tests/scripts
    - Create a script to measure executing `EnsemblePredictor` time
    - Create a script to measure CPU context switches (if possible via `psutil`) or just load
  - [x] 1.2 Implement `worker_initializer` in `portfolio_optimization.py`
    - Create a function to set `OMP_NUM_THREADS`, `TF_NUM_INTRAOP_THREADS`, `MKL_NUM_THREADS` to "1"
    - Integrate this initializer into `ProcessPoolExecutor`
  - [x] 1.3 Modify `LSTMModel` in `forecast_models.py`
    - Add threading configuration in `train` method to force TensorFlow to single-threaded mode per process
    - Ensure `tf.config` settings are applied before any other TF operations in the worker
  - [x] 1.4 Modify `XGBoostModel` in `forecast_models.py`
    - Update `XGBRegressor` initialization to use `n_jobs=1` or `nthread=1`
  - [x] 1.5 Validate configuration application
    - Run the benchmark script from 1.1 to verify runtime improvement and CPU usage pattern (should see higher efficiency, less system time)

**Acceptance Criteria:**
- `pool_initializer` is correctly setting environment variables
- `LSTMModel` and `XGBoostModel` explicitly restrict thread counts to 1
- Benchmark shows reduced runtime (aiming for 30%+ improvement)

#### Task Group 2: Process Pool Tuning
**Assigned implementer:** api-engineer
**Dependencies:** Task Group 1

- [x] 2.0 Tune Parallelism Parameters
  - [x] 2.1 Write a parameterized benchmark test
    - Script that runs `ml_forecast_returns` with different `batch_size` and `max_workers`
  - [x] 2.2 Optimize `max_workers` calculation in `portfolio_optimization.py`
    - Update the `max_workers` logic to possibly use `cpu_count()` directly or a fixed ratio safe for memory
    - Test if `max_workers` needs to be slightly lower than core count to leave room for OS
  - [x] 2.3 Optimize `batch_size` in `ml_forecast_returns`
    - Experiment with larger batch sizes to reduce overhead of process spawning/result pickling
  - [x] 2.4 Verify forecasts remain identical
    - Compare output of optimized run vs baseline (saved) to ensure `l1_tolerance` of 0
  
**Acceptance Criteria:**
- `max_workers` and `batch_size` are tuned for optimal throughput on standard dev machine
- Output values match exactly (numerical precision preserved)

### Testing

#### Task Group 3: Performance Verification
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1-2

- [x] 3.0 Verify Performance and Regression
  - [x] 3.1 Create a dedicated performance test suite
    - Test case that runs a full `optimize_portfolio` call with 20 dummy tickers
    - Assert runtime is under a specific threshold (e.g., < X seconds based on baseline)
  - [x] 3.2 Regression testing for Forecast Values
    - Test case that mocks price data and asserts equal output from `EnsemblePredictor` before/after optimization changes
    - Verify `Black-Litterman` outputs are consistent
  - [x] 3.3 Execute validation
    - Run the new performance tests
    - Confirm CPU profile is healthy (not 100% kernel/system time)

**Acceptance Criteria:**
- Performance test passes within target time
- Regression tests pass (no change in values)
- No memory leaks detected during repeated runs

## Execution Order

Recommended implementation sequence:
1. Backend Optimization - Environment & Models (Task Group 1)
2. Backend Optimization - Tuning (Task Group 2)
3. Testing - Performance Verification (Task Group 3)
