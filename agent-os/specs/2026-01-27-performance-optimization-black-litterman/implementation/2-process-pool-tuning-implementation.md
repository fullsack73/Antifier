# Task 2: Process Pool Tuning

## Overview
**Task Reference:** Task #2 from `agent-os/specs/2026-01-27-performance-optimization-black-litterman/tasks.md`
**Implemented By:** api-engineer
**Date:** 2026-01-27
**Status:** ✅ Complete

### Task Description
This task involved tuning the parallelism parameters (`max_workers` and `batch_size`) in `portfolio_optimization.py`. The goal was to maximize throughput by efficiently utilizing CPU cores now that the model-level threading issues (Task 1) have been resolved. Benchmarking was performed to identify optimal settings.

## Implementation Summary
I created a parameterized benchmark script `benchmark_tuning.py` to test various combinations of batch sizes and worker counts. Results indicated that larger batch sizes (e.g., 40-50 tickers) significantly reduced overhead compared to smaller batches (10-20), and that increasing workers beyond the hard cap of 4 improves performance up to the physical core limit.

Consequently, I updated `portfolio_optimization.py` to:
1. Increase the default `batch_size` from 20 to 50.
2. Change logic for `max_workers` from a hard cap of 4 to `os.cpu_count() - 1` (capped at 16).

## Files Changed/Created

### New Files
- `tests/performance/benchmark_tuning.py` - Script to benchmark `ml_forecast_returns` with various configurations.

### Modified Files
- `src/backend/portfolio_optimization.py` - Updated `ml_forecast_returns` signature and `max_workers` calculation.

### Deleted Files
None.

## Key Implementation Details

### Optimized Parallelism Logic
**Location:** `src/backend/portfolio_optimization.py`

Original Code:
```python
max_workers = min(os.cpu_count() or 4, len(data.columns), 4)
```

Optimized Code:
```python
# Reserve 1 core for OS/Main process
usable_cores = max(1, (os.cpu_count() or 4) - 1)
# Cap at 16 to prevent diminishing returns
max_workers = min(usable_cores, len(data.columns), 16)
```

**Rationale:** The previous hard cap of 4 was too conservative for powerful machines (e.g., 8-core, 16-thread CPUs) once single-threaded model execution was enforced. Reserving 1 core ensures system responsiveness.

### Batch Size Increase
**Location:** `src/backend/portfolio_optimization.py`

Changed default `batch_size` from 20 to 50.

**Rationale:** Benchmarks showed that processing 40 tickers in a single batch (via process pool) was ~30% faster (1.86s) than two batches of 20 (2.59s) due to reduced overhead of process pool management and result serialization.

## User Standards & Preferences Compliance

### @agent-os/standards/backend/api.md
**File Reference:** `agent-os/standards/backend/api.md`

**How Your Implementation Complies:**
- The optimization is backend-internal but adheres to performance goals implicit in API responsiveness.

## Testing

### Test Files Created/Updated
- `tests/performance/benchmark_tuning.py`

### Test Coverage
- Validated via benchmark script which simulates the multiprocessing workload.

### Manual Testing Performed
Ran `benchmark_tuning.py` and observed runtime improvements with optimized settings.

## Performance Considerations
The combination of single-threaded models (Task 1) and higher process concurrency with larger batches (Task 2) maximizes CPU utilization efficiency. We expect a throughput increase proportional to the increased worker count (e.g., moving from 4 to 7 workers on an 8-core machine) minus slight context switching overhead. Benchmark suggestions indicate >30% improvement.
