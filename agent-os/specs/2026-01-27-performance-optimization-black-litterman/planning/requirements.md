# Spec Requirements: performance-optimization-black-litterman

## Initial Description
after replacing MPT with Black-Litterman model, winner-takes-all decision between 3 models with ensemble method, and implementing usage of log return, I have noticed significant speed decrease in running #file:portfolio_optimization.py  and i need to know why this happens and possibly fix it.

## Requirements Discussion

### First Round Questions

**Q1:** You mentioned a "significant speed decrease". Could you quantify this?
**Answer:** now it takes approx. two times than it used to take.

**Q2:** You identified "winner-takes-all decision between 3 models" as a change. Does this mean for *every single ticker*, we are now training/evaluating 3 distinct models (e.g., ARIMA, LSTM, Prophet) to pick the best one?
**Answer:** no, it was ORIGINALLY a winner-takes-all method where the best model gets to decide the forecast result. now we use ensemble. you can check #file:forecast_models.py for details. and yes, we train and validate every ticker in the list.

**Q3:** I suspect the bottleneck is in the ML forecasting phase (generating views for Black-Litterman) rather than the Black-Litterman formula itself. Is that consistent with your specific observations?
**Answer:** yes. the bottleneck seems to happen at the ML forecasting phase.

**Q4:** Regarding "implementing usage of log return": Are you converting prices to log returns *before* passing them to the models, and if so, are you converting the predictions back to simple returns for the portfolio optimizer?
**Answer:** you can read #file:forecast_models.py about how the price data is handled. i think that would clarify things better (Note: Code confirms log return conversion happens within the models).

**Q5:** I see `ProcessPoolExecutor` is already being used for parallelism. During the slow execution, do you notice high CPU usage (all cores maxed out) or low CPU usage (waiting on tasks)?
**Answer:** i see high CPU usage(almost 100%) across all the cores.

**Q6:** I'm assuming we want to maintain the accuracy of the "3-model ensemble" but optimize its runtime. Is it acceptable to trade off a small amount of accuracy for speed (e.g., using a lighter model for stable stocks), or is strictly "best model wins" required?
**Answer:** DO NOT change how it forecasts. current ensemble method will remain.

**Q7:** Are there specific tickers or groups (e.g., S&P 500 vs. small list) where this slowness is most critical?
**Answer:** the more tickers there are, slower it becomes.

### Existing Code to Reference
No similar existing features identified for reference.

### Follow-up Questions
No follow-up questions were needed as the performance bottleneck source (Ensemble vs Winner-Takes-All) and constraints (Must keep Ensemble) are clear.

## Visual Assets

### Files Provided:
No visual assets provided.

## Requirements Summary

### Functional Requirements
- **Diagnostic:** Provide a clear explanation of why the performance decreased (Root cause analysis).
- **Optimization:** Reduce the execution time of `portfolio_optimization.py` without altering the fundamental forecasting methodology (Ensemble of ELISA/LSTM/XGBoost).
- **Target:** Aim to reduce the current "2x slower" runtime, ideally bringing it closer to previous performance levels if possible via system/resource optimization.

### Reusability Opportunities
- `ProcessPoolExecutor` configuration in `portfolio_optimization.py`.
- `ML` model implementations in `forecast_models.py` (specifically resource management in LSTM/TensorFlow).

### Scope Boundaries
**In Scope:**
- Optimizing resource usage (CPU/Memory).
- Tuning parallelism configurations (Workers, Batch sizes).
- Reducing overhead in model instantiation (e.g., TensorFlow session management).
- Optimizing data handling (log return calculations) if consistent with logic.
- Caching improvements.

**Out of Scope:**
- Changing the forecasting algorithms (e.g., swapping LSTM for a simpler model).
- Removing models from the ensemble.
- Changing the Black-Litterman logic (unless it's purely code performance, but user indicated bottleneck is ML).

### Technical Considerations
- **Root Cause Hypothesis:** Moving from "select best of 3" (if that meant early stopping or just one model runs?) or even if it meant "run 3, pick 1", the new "run 3, average 3" forces all 3 to complete. If the previous version optimized by not running all 3 for everyone, that explains it. However, user said "originally winner-takes-all... now ensemble", implying we ran 3 before too? 
    - *Correction:* User said "originally winner takes all... now ensemble". If "winner takes all" implied running all 3 to find the winner, then the valid workload is similar (3 runs). If the slowdown is 2x, it might be due to `ProcessPoolExecutor` overhead combined with `auto_arima` + `TensorFlow` resource contention (Context switching) when forced to return distinct values for ensemble rather than just a selection. 
- **High CPU (100%):** Indicates CPU saturation. `auto_arima` is single-threaded usually unless `n_jobs` is set. `TensorFlow` tries to grab all cores. 
- **Conflict:** Multiple processes each trying to use multiple cores (via TF or numpy BLAS) causes thrashing. 
- **Optimization Strategy:**
    - Restrict TensorFlow to single-thread per process.
    - Tune `ProcessPoolExecutor` max_workers.
    - Check `auto_arima` settings.
