import importlib
import io
from pathlib import Path

import pytest


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG", "development")
    monkeypatch.setenv("DEV_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("BASE_STORAGE_PATH", str((tmp_path / "storage").resolve()))
    monkeypatch.setenv("UPLOAD_FOLDER", str((tmp_path / "uploads").resolve()))
    monkeypatch.setenv("TEMP_UPLOAD_PATH", str((tmp_path / "temp").resolve()))
    monkeypatch.setenv("TRASH_PATH", str((tmp_path / "trash").resolve()))
    monkeypatch.setenv("USE_HTTPS", "0")
    monkeypatch.setenv("SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SERVER_PORT", "5056")

    import config as config_module
    import app as app_module

    importlib.reload(config_module)
    importlib.reload(app_module)

    application = app_module.create_app("development")
    application.config.update(TESTING=True)

    from app.extensions import db

    yield application, application.test_client(), db

    with application.app_context():
        db.session.remove()
        db.drop_all()


def login_admin(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
    )
    assert response.status_code == 302


def get_admin_root_folder(db):
    from app.models.file import Folder
    from app.models.user import User

    admin = User.query.filter_by(username="admin").first()
    return Folder.query.filter_by(user_id=admin.id, parent_id=None, is_deleted=False).first()


def create_file_record(db, root_folder, filename, original_filename):
    from flask import current_app
    from app.models.file import File
    from app.models.user import User

    admin = User.query.filter_by(username="admin").first()
    file_path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"seed")

    file_record = File(
        filename=filename,
        original_filename=original_filename,
        file_path=str(file_path),
        size=4,
        file_type="document",
        user_id=admin.id,
        folder_id=root_folder.id,
    )
    db.session.add(file_record)
    db.session.commit()
    return file_record


def test_create_folder_accepts_unicode_names(app_client):
    application, client, db = app_client
    login_admin(client)

    with application.app_context():
        root_folder = get_admin_root_folder(db)
        root_folder_id = root_folder.id
        root_user_id = root_folder.user_id

    response = client.post(
        "/folders/create",
        data={"folder_name": "项目 资料", "parent_id": root_folder_id},
        follow_redirects=True,
    )

    assert response.status_code == 200

    with application.app_context():
        from app.models.file import Folder

        created_folder = Folder.query.filter_by(
            user_id=root_user_id,
            parent_id=root_folder_id,
            name="项目 资料",
        ).first()
        assert created_folder is not None


def test_rename_file_preserves_unicode_and_extension(app_client):
    application, client, db = app_client
    login_admin(client)

    with application.app_context():
        root_folder = get_admin_root_folder(db)
        file_record = create_file_record(db, root_folder, "old.txt", "old.txt")
        file_id = file_record.id

    response = client.post(
        f"/files/rename/{file_id}",
        data={"new_name": "报告"},
        follow_redirects=True,
    )

    assert response.status_code == 200

    with application.app_context():
        from app.models.file import File

        renamed_file = File.query.get(file_id)
        assert renamed_file.original_filename == "报告.txt"


def test_search_files_trims_query_and_returns_json(app_client):
    application, client, db = app_client
    login_admin(client)

    with application.app_context():
        root_folder = get_admin_root_folder(db)
        create_file_record(db, root_folder, "quarterly-report.txt", "Quarterly Report.txt")

    response = client.get(
        "/files/search?query=%20Quarterly%20",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["query"] == "Quarterly"
    assert payload["total_count"] == 1
    assert "Quarterly Report.txt" in payload["html"]


def test_upload_file_cleans_saved_file_when_commit_fails(app_client, monkeypatch):
    application, client, db = app_client
    login_admin(client)

    with application.app_context():
        root_folder = get_admin_root_folder(db)
        root_folder_id = root_folder.id

    import app.routes.files as files_routes

    def failing_commit():
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(files_routes.db.session, "commit", failing_commit)

    response = client.post(
        "/files/upload",
        data={
            "folder_id": root_folder_id,
            "files[]": (io.BytesIO(b"test-content"), "sample.txt"),
        },
        content_type="multipart/form-data",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 500

    upload_folder = Path(application.config["UPLOAD_FOLDER"]) / str(root_folder_id)
    assert not upload_folder.exists() or not any(upload_folder.iterdir())
