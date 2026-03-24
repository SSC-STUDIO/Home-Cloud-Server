import importlib


def create_test_app(tmp_path, monkeypatch, admin_password=None):
    monkeypatch.setenv("APP_CONFIG", "development")
    monkeypatch.setenv("DEV_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("BASE_STORAGE_PATH", str((tmp_path / "storage").resolve()))
    monkeypatch.setenv("UPLOAD_FOLDER", str((tmp_path / "uploads").resolve()))
    monkeypatch.setenv("TEMP_UPLOAD_PATH", str((tmp_path / "temp").resolve()))
    monkeypatch.setenv("TRASH_PATH", str((tmp_path / "trash").resolve()))
    monkeypatch.setenv("USE_HTTPS", "0")
    monkeypatch.setenv("SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SERVER_PORT", "5056")
    if admin_password is None:
        monkeypatch.delenv("DEFAULT_ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("DEFAULT_ADMIN_PASSWORD_FILE", raising=False)
    else:
        monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", admin_password)

    import config as config_module
    import app as app_module

    importlib.reload(config_module)
    importlib.reload(app_module)

    return app_module.create_app("development")


def test_initialize_db_uses_configured_admin_password(tmp_path, monkeypatch):
    application = create_test_app(tmp_path, monkeypatch, admin_password="ConfigSecret!234")
    client = application.test_client()

    response = client.post(
        "/login",
        data={"username": "admin", "password": "ConfigSecret!234"},
        follow_redirects=False,
    )

    assert response.status_code == 302


def test_initialize_db_does_not_use_legacy_default_password(tmp_path, monkeypatch):
    application = create_test_app(tmp_path, monkeypatch, admin_password=None)
    client = application.test_client()

    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
    )

    assert response.status_code == 200


def test_healthz_uses_version_from_config(tmp_path, monkeypatch):
    application = create_test_app(tmp_path, monkeypatch, admin_password="ConfigSecret!234")
    client = application.test_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json()["version"] == application.config["APP_VERSION"]


def test_initialize_db_creates_system_metrics_table(tmp_path, monkeypatch):
    application = create_test_app(tmp_path, monkeypatch, admin_password="ConfigSecret!234")

    with application.app_context():
        from sqlalchemy import inspect
        from app.extensions import db

        tables = inspect(db.engine).get_table_names()

    assert "system_metrics" in tables
