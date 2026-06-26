import builtins
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_installer_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "installer.py"
    spec = importlib.util.spec_from_file_location("antifier_installer", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_launcher_does_not_pause(tmp_path):
    installer = load_installer_module()
    generator = installer.LauncherGenerator(
        tmp_path,
        SimpleNamespace(system="Windows"),
    )

    launcher_path = generator.generate_windows_launcher()

    assert "pause" not in launcher_path.read_text().lower()


def test_existing_installation_updates_without_prompt(tmp_path, monkeypatch):
    installer_module = load_installer_module()
    installer = installer_module.Installer(install_dir=tmp_path)
    installer.config_manager.create_config(
        {
            "installation_date": "2026-01-01T00:00:00",
            "last_update": "2026-01-01T00:00:00",
            "python_version": "3.11.0",
            "nodejs_version": "v20.0.0",
        }
    )

    monkeypatch.setattr(
        builtins,
        "input",
        lambda: (_ for _ in ()).throw(AssertionError("input() should not be called")),
    )

    assert installer.check_for_updates() is True


def test_missing_windows_compiler_does_not_prompt_by_default(tmp_path, monkeypatch):
    installer_module = load_installer_module()
    installer = installer_module.Installer(install_dir=tmp_path)
    installer.platform.system = "Windows"
    installer.platform.get_platform_name = lambda: "Windows"

    monkeypatch.setattr(installer.validator, "check_nodejs", lambda: (True, "v20.0.0"))
    monkeypatch.setattr(installer.validator, "check_python", lambda: (True, "3.11.0"))
    monkeypatch.setattr(installer.validator, "check_disk_space", lambda: (True, 10.0))
    monkeypatch.setattr(installer.validator, "check_write_permissions", lambda: True)
    monkeypatch.setattr(installer.validator, "check_cpp_compiler", lambda: False)
    monkeypatch.setattr(
        installer.validator,
        "install_cpp_compiler",
        lambda: (_ for _ in ()).throw(AssertionError("Build Tools should be opt-in")),
    )
    monkeypatch.setattr(
        builtins,
        "input",
        lambda: (_ for _ in ()).throw(AssertionError("input() should not be called")),
    )

    assert installer.validate_prerequisites() is True
