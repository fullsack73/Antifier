import sys
import types


def _install_missing_pmdarima_stub():
    module = types.ModuleType("pmdarima")

    def auto_arima(*_args, **_kwargs):
        raise RuntimeError("pmdarima is not installed in this test environment")

    module.auto_arima = auto_arima
    sys.modules["pmdarima"] = module


try:
    import pmdarima  # noqa: F401
except Exception:
    _install_missing_pmdarima_stub()
