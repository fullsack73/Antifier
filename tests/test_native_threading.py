import native_threading


def test_get_ml_worker_limit_caps_windows_to_safe_default(monkeypatch):
    monkeypatch.setattr(native_threading.platform, "system", lambda: "Windows")
    monkeypatch.setattr(native_threading.os, "cpu_count", lambda: 16)
    monkeypatch.delenv("ANTIFIER_ML_MAX_WORKERS", raising=False)
    monkeypatch.delenv("ANTIFIER_WINDOWS_ML_MAX_WORKERS", raising=False)

    assert native_threading.get_ml_worker_limit(100) == 2


def test_get_ml_worker_limit_allows_explicit_override(monkeypatch):
    monkeypatch.setattr(native_threading.platform, "system", lambda: "Windows")
    monkeypatch.setattr(native_threading.os, "cpu_count", lambda: 16)
    monkeypatch.setenv("ANTIFIER_ML_MAX_WORKERS", "4")

    assert native_threading.get_ml_worker_limit(100) == 4
