from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DEFAULT_TITLE = "Login - Home Cloud Server"
DEFAULT_TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "60"))
DEFAULT_LOG_DIR = Path(
    os.environ.get(
        "SMOKE_LOG_DIR",
        r"C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server",
    )
)


def _get_smoke_setting(name: str, default: str) -> str:
    value = os.environ.get(f"SMOKE_{name}")
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _get_smoke_bool(name: str, default: bool) -> bool:
    value = os.environ.get(f"SMOKE_{name}")
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def _find_edge() -> str | None:
    edge = shutil.which("msedge")
    if edge:
        return edge

    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    return None


def _wait_for_server(url: str, process: subprocess.Popen, timeout: int) -> requests.Response:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    last_status: int | None = None

    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early with code {process.returncode}.")
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                return response
            last_status = response.status_code
        except Exception as exc:  # pragma: no cover - network wait loop
            last_error = exc
        time.sleep(1)

    if last_status is not None:
        raise RuntimeError(f"Server did not return 200 within {timeout}s (last status {last_status}).")
    raise RuntimeError(f"Server did not respond within {timeout}s: {last_error}")


def _extract_title(html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()


def _take_screenshot(edge_path: str, url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_args = [
        edge_path,
        "--disable-gpu",
        "--window-size=1280,720",
        f"--screenshot={output_path}",
        url,
    ]

    for headless_flag in ("--headless=new", "--headless"):
        result = subprocess.run(base_args + [headless_flag], capture_output=True, text=True)
        if result.returncode == 0:
            return

    raise RuntimeError("Edge headless screenshot failed. Ensure Edge supports --headless/--screenshot.")


def _find_python(repo_root: Path) -> str:
    for candidate in (
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / "venv" / "Scripts" / "python.exe",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    output_path = repo_root / "output" / "ui" / "home-cloud.png"

    edge_path = _find_edge()
    if not edge_path:
        raise RuntimeError("Microsoft Edge not found. Install Edge or add msedge to PATH.")

    env = os.environ.copy()
    smoke_host = _get_smoke_setting("SERVER_HOST", DEFAULT_HOST)
    smoke_port = _get_smoke_setting("SERVER_PORT", str(DEFAULT_PORT))
    smoke_app_config = _get_smoke_setting("APP_CONFIG", "development")
    smoke_use_https = _get_smoke_bool("USE_HTTPS", False)

    env["USE_HTTPS"] = "1" if smoke_use_https else "0"
    env["SERVER_HOST"] = smoke_host
    env["HOST"] = smoke_host
    env["SERVER_PORT"] = smoke_port
    env["PORT"] = smoke_port
    env["APP_CONFIG"] = smoke_app_config
    env["APP_USE_RELOADER"] = "0"

    # 0.0.0.0 is a listen address, not connectable — always use 127.0.0.1 for the client
    connect_host = DEFAULT_HOST if smoke_host == "0.0.0.0" else smoke_host
    scheme = "https" if smoke_use_https else "http"
    url = f"{scheme}://{connect_host}:{smoke_port}/"

    python_bin = _find_python(repo_root)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = Path(
        _get_smoke_setting(
            "LOG_PATH",
            str(DEFAULT_LOG_DIR / f"smoke-server-{timestamp}.log"),
        )
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("w", encoding="utf-8") as log_file:
        server_process = subprocess.Popen(
            [python_bin, "main.py"],
            cwd=repo_root,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            try:
                response = _wait_for_server(url, server_process, DEFAULT_TIMEOUT)
            except Exception as exc:
                raise RuntimeError(f"{exc} (see log {log_path})") from exc

            if response.status_code != 200:
                raise RuntimeError(f"GET / returned {response.status_code}")

            title = _extract_title(response.text)
            if title != DEFAULT_TITLE:
                raise RuntimeError(f"Unexpected title: '{title}' (expected '{DEFAULT_TITLE}')")

            _take_screenshot(edge_path, url, output_path)
            print(f"Smoke test OK. Screenshot saved to: {output_path}")
        finally:
            server_process.terminate()
            try:
                server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_process.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
