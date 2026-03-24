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


def test_app_version_reads_version_file(monkeypatch, tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("9.9.9\n", encoding="utf-8")

    config = reload_config(monkeypatch, "Linux")
    monkeypatch.setattr(config, "VERSION_FILE", version_file)

    assert config.read_version_file() == "9.9.9"


def test_app_version_falls_back_when_version_file_missing(monkeypatch, tmp_path):
    config = reload_config(monkeypatch, "Linux")
    monkeypatch.setattr(config, "VERSION_FILE", tmp_path / "missing-version")

    assert config.read_version_file(default="unknown") == "unknown"


def test_default_admin_password_reads_from_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "admin-password.txt"
    secret_file.write_text("file-secret\n", encoding="utf-8")
    monkeypatch.delenv("DEFAULT_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD_FILE", str(secret_file))

    config = reload_config(monkeypatch, "Linux")

    assert config.read_secret_setting("DEFAULT_ADMIN_PASSWORD") == "file-secret"
