import importlib
import io
import socket
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from requests import Response


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
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "TestAdmin!234")

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


def login_admin(client, password="TestAdmin!234"):
    response = client.post(
        "/login",
        data={"username": "admin", "password": password},
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


def make_response(url, status_code=200, headers=None, body=b"payload", raise_on_iter=False):
    response = Response()
    response.status_code = status_code
    response.headers.update(headers or {})
    response.raw = io.BytesIO(body)
    response._content = body
    response.url = url
    response.request = requests.Request('GET', url).prepare()
    if raise_on_iter:
        def iter_content(chunk_size=1, decode_unicode=False):
            raise ValueError("Blocked remote address")
    else:
        def iter_content(chunk_size=1, decode_unicode=False):
            yield body
    response.iter_content = iter_content
    return response


def fake_getaddrinfo_factory(address_map):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        values = address_map.get(host)
        if values is None:
            raise socket.gaierror(host)
        if not values:
            raise AssertionError(f"No remaining addresses for {host}")
        next_value = values.pop(0)
        if isinstance(next_value, Exception):
            raise next_value
        if isinstance(next_value, list):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port or 0))
                for ip in next_value
            ]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (next_value, port or 0))]

    return fake_getaddrinfo


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


def test_remote_download_blocks_dns_rebinding_target(app_client, monkeypatch):
    application, client, db = app_client
    login_admin(client)

    with application.app_context():
        root_folder = get_admin_root_folder(db)
        root_folder_id = root_folder.id

    import app.routes.files as files_routes

    response = make_response(
        "http://93.184.216.34/report.txt",
        headers={"Content-Length": "7", "Content-Type": "text/plain"},
        body=b"blocked",
        raise_on_iter=True,
    )

    with patch.object(files_routes, "create_remote_download_session") as create_session_mock:
        session_mock = create_session_mock.return_value.__enter__.return_value
        session_mock.get.return_value = response
        monkeypatch.setattr(
            files_routes.socket,
            "getaddrinfo",
            fake_getaddrinfo_factory({"safe.example": [["93.184.216.34", "127.0.0.1"]]}),
        )
        result = client.post(
            "/files/remote_download",
            data={"file_url": "http://safe.example/report.txt", "folder_id": root_folder_id},
            follow_redirects=True,
        )

    assert result.status_code == 200
    assert b"File downloaded successfully" not in result.data
    assert b"Blocked remote address" in result.data
    assert session_mock.get.call_count == 0


def test_prepare_remote_request_uses_direct_connect_url(monkeypatch):
    import app.routes.files as files_routes

    monkeypatch.setattr(
        files_routes.socket,
        "getaddrinfo",
        fake_getaddrinfo_factory({"safe.example": ["93.184.216.34"]}),
    )

    remote_request = files_routes.prepare_remote_request("http://safe.example/report.txt")

    assert remote_request["direct_url"] == "http://93.184.216.34/report.txt"
    assert remote_request["headers"] == {"Host": "safe.example"}
    assert remote_request["verify"] == "safe.example"


def test_resolve_remote_connect_target_rejects_mixed_dns_answers(monkeypatch):
    import app.routes.files as files_routes

    parsed = files_routes.validate_remote_download_url("http://safe.example/report.txt")

    monkeypatch.setattr(
        files_routes.socket,
        "getaddrinfo",
        fake_getaddrinfo_factory({"safe.example": [["93.184.216.34", "127.0.0.1"]]}),
    )

    with pytest.raises(ValueError, match="Blocked remote address"):
        files_routes.resolve_remote_connect_target(parsed)


def test_remote_download_blocks_redirect_to_private_host(app_client, monkeypatch):
    application, client, db = app_client
    login_admin(client)

    with application.app_context():
        root_folder = get_admin_root_folder(db)
        root_folder_id = root_folder.id

    import app.routes.files as files_routes

    redirect_response = make_response(
        "http://93.184.216.34/start",
        status_code=302,
        headers={"Location": "http://internal.example/secret.txt"},
        body=b"",
    )

    with patch.object(files_routes, "create_remote_download_session") as create_session_mock:
        session_mock = create_session_mock.return_value.__enter__.return_value
        session_mock.get.return_value = redirect_response
        monkeypatch.setattr(
            files_routes.socket,
            "getaddrinfo",
            fake_getaddrinfo_factory(
                {
                    "safe.example": ["93.184.216.34"],
                    "internal.example": ["127.0.0.1"],
                }
            ),
        )
        result = client.post(
            "/files/remote_download",
            data={"file_url": "http://safe.example/start", "folder_id": root_folder_id},
            follow_redirects=True,
        )

    assert result.status_code == 200
    assert b"Blocked remote address" in result.data
    assert session_mock.get.call_count == 1
    called_url = session_mock.get.call_args.args[0]
    called_headers = session_mock.get.call_args.kwargs["headers"]
    assert called_url == "http://93.184.216.34/start"
    assert called_headers["Host"] == "safe.example"


