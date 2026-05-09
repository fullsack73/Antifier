import os
import platform


NATIVE_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "TF_NUM_INTRAOP_THREADS",
    "TF_NUM_INTEROP_THREADS",
)


def configure_native_threading(thread_limit="1", force=False):
    """Limit native math/ML library thread pools before heavy imports happen."""
    for var_name in NATIVE_THREAD_ENV_VARS:
        if force:
            os.environ[var_name] = str(thread_limit)
        else:
            os.environ.setdefault(var_name, str(thread_limit))


def is_windows():
    return platform.system() == "Windows"


def get_ml_worker_limit(ticker_count, default_non_windows_cap=16):
    """Return a conservative worker count for ML forecasting."""
    cpu_count = os.cpu_count() or 4
    usable_cores = max(1, cpu_count - 1)

    env_limit = os.environ.get("ANTIFIER_ML_MAX_WORKERS")
    if env_limit:
        try:
            configured_limit = max(1, int(env_limit))
            return min(configured_limit, usable_cores, max(1, ticker_count))
        except ValueError:
            pass

    if is_windows():
        windows_limit = os.environ.get("ANTIFIER_WINDOWS_ML_MAX_WORKERS", "2")
        try:
            windows_limit = max(1, int(windows_limit))
        except ValueError:
            windows_limit = 2
        return min(windows_limit, usable_cores, max(1, ticker_count))

    return min(usable_cores, max(1, ticker_count), default_non_windows_cap)
