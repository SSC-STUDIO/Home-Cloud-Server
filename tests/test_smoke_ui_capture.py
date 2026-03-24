import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_ui_capture.py"
spec = importlib.util.spec_from_file_location("smoke_ui_capture", SCRIPT_PATH)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_get_smoke_setting_uses_namespace(monkeypatch):
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("SMOKE_SERVER_HOST", "127.0.0.1")

    assert smoke._get_smoke_setting("SERVER_HOST", smoke.DEFAULT_HOST) == "127.0.0.1"


def test_get_smoke_setting_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("SMOKE_SERVER_PORT", raising=False)

    assert smoke._get_smoke_setting("SERVER_PORT", "5000") == "5000"


def test_get_smoke_bool_reads_namespace(monkeypatch):
    monkeypatch.setenv("SMOKE_USE_HTTPS", "true")

    assert smoke._get_smoke_bool("USE_HTTPS", False) is True


def test_get_smoke_bool_falls_back(monkeypatch):
    monkeypatch.delenv("SMOKE_USE_HTTPS", raising=False)

    assert smoke._get_smoke_bool("USE_HTTPS", False) is False
