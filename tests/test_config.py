import importlib
import sys
from pathlib import Path


def reload_config(monkeypatch, system_name: str):
    """Reload config module with a mocked platform.system value."""
    monkeypatch.setattr("platform.system", lambda: system_name)
    sys.modules.pop("config", None)
    return importlib.import_module("config")


def test_base_storage_path_uses_env_override(monkeypatch, tmp_path):
    override_path = tmp_path / "custom-storage"
    monkeypatch.setenv("BASE_STORAGE_PATH", str(override_path))
    config = reload_config(monkeypatch, "Linux")

    assert config.get_base_storage_path() == override_path


def test_windows_storage_falls_back_to_home_when_d_drive_missing(monkeypatch):
    monkeypatch.delenv("BASE_STORAGE_PATH", raising=False)
    config = reload_config(monkeypatch, "Windows")

    monkeypatch.setattr(config.Path, "home", lambda: Path("/home/test-user"))
    monkeypatch.setattr(config.Path, "exists", lambda self: False)

    assert config.get_base_storage_path() == Path("/home/test-user/cloud_storage")


def test_linux_storage_prefers_mnt_cloud_storage(monkeypatch):
    monkeypatch.delenv("BASE_STORAGE_PATH", raising=False)
    config = reload_config(monkeypatch, "Linux")

    monkeypatch.setattr(config.os.path, "exists", lambda p: p == "/mnt/cloud_storage")

    assert config.get_base_storage_path() == Path("/mnt/cloud_storage")


def test_ssl_paths_linux_vs_non_linux(monkeypatch):
    linux_config = reload_config(monkeypatch, "Linux")
    assert linux_config.Config.SSL_CERT == "/etc/ssl/certs/home-cloud.crt"
    assert linux_config.Config.SSL_KEY == "/etc/ssl/private/home-cloud.key"

    darwin_config = reload_config(monkeypatch, "Darwin")
    assert Path(darwin_config.Config.SSL_CERT).parts[-2:] == ("ssl", "home-cloud.crt")
    assert Path(darwin_config.Config.SSL_KEY).parts[-2:] == ("ssl", "home-cloud.key")
