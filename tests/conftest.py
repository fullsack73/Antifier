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

# Candidate state is durable in production; test cases must never share campaigns/predictions.
import pytest

@pytest.fixture(autouse=True)
def isolated_candidate_store(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTIFIER_CANDIDATE_DB', str(tmp_path/'candidate-search.sqlite3'))
    monkeypatch.setenv('ANTIFIER_BACKTEST_CHECKPOINT_DIR', str(tmp_path/'backtest-jobs'))
