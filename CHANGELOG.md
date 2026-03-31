# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [0.1.11] - 2026-03-31

### Fixed
- Hardened `remote_download` SSRF protection by resolving each request target at connect time, blocking any hostname whose DNS answers include private, loopback, link-local, or reserved addresses before direct-IP fetches proceed.
- Extended the same destination guard to manual redirect handling so remote downloads cannot be bounced from a public URL to an internal/private host.

## [0.1.10] - 2026-03-23

### Fixed
- Fixed smoke_ui_capture.py port mismatch: aligned DEFAULT_PORT from 5055 to 5000 to match .env SERVER_PORT and actual server startup, resolving "RuntimeError: Server did not respond within 60s" and WinError 10061 connection failures.
- Fixed WinError 10049 by ensuring smoke test connects to 127.0.0.1 instead of 0.0.0.0 bind address.
- Fixed admin bootstrap to require a configured `DEFAULT_ADMIN_PASSWORD` or generate a one-time password instead of falling back to the legacy default credential.
- Fixed database initialization to create the `system_metrics` table during startup.

### Changed
- Smoke test now reliably connects to 127.0.0.1:5000 for UI screenshot capture.
- Enhanced smoke test to handle SERVER_HOST=0.0.0.0 by mapping it to 127.0.0.1 for client connections.
- Application runtime version now reads from `VERSION` so the UI, health check, and package metadata stay aligned.

### Evidence
- Smoke log: `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\smoke-server-20260323-183020.log`
- Screenshot: `C:\Users\96152\My-Project\Active\Websites\Home-Cloud-Server\output\ui\home-cloud.png` (462K, 2026-03-23 18:30)

## [0.1.9] - 2026-03-20

### Changed
- Refactored UI/file-manager templates, route handling, and frontend asset split for the current dirty-tree release gate pass.

### Fixed
- Re-ran UI smoke capture, refreshed screenshot evidence, and rechecked the smoke shutdown path for `WinError 10038` regression.
- Moved/confirmed process files stay outside the repo root and reinforced `.gitignore` entries for `task_plan.md`, `findings.md`, `progress.md`, `team-board.md`, and `store.json`.
- Repaired the `CHANGELOG.md` top section so the release entry is again a valid version heading and matches `VERSION` / `pyproject.toml` at `0.1.9`.

### Added
- Refreshed release-gate evidence references:
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\refactor-tree-review-latest.patch`
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\smoke-ui-capture-refactor-baseline-latest.log`
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\git-status-after-refactor-baseline-latest.log`
  - `C:\Users\96152\My-Project\Active\Websites\Home-Cloud-Server\output\ui\home-cloud.png`
- 2026-03-22 queue-only validation evidence refresh:
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\git-status-refactor-acceptance-refresh-latest.log`
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\git-diff-stat-refactor-acceptance-refresh-latest.log`
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\refactor-acceptance-refresh-latest.patch`
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\smoke-ui-refactor-acceptance-refresh-latest.log`
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\git-diff-cached-name-status-refactor-stage-cut-latest.log`
  - `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\git-status-after-refactor-stage-cut-latest.log`

## [0.1.6] - 2026-03-14

### Fixed
- smoke 脚本现在会显式关闭 Flask reloader，避免 UI smoke 在本地截图完成后因为调试子进程残留而挂住。
- `main.py` 新增 `APP_USE_RELOADER` 运行时开关，便于 smoke 或其他自动化任务在保留开发配置时禁用 reloader。

### Changed
- UI 证据已刷新到 `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\home-cloud-20260314-1227.png`。

## [0.1.5] - 2026-03-13

### Fixed
- smoke script now detects early server exit and uses configurable timeout for readiness.
- smoke script writes server stdout/stderr to SMOKE_LOG_PATH/SMOKE_LOG_DIR and includes log path on failures.
- smoke script now prefers local venv Python when available to avoid missing dependencies.
- wait for `GET /` to return 200 before taking UI screenshot in smoke.

### Added
- configurable `SMOKE_LOG_PATH` / `SMOKE_LOG_DIR` for smoke diagnostics.

### Changed
- ignore UI output screenshots under `output/ui/*.png` to avoid committing evidence artifacts.
- UI evidence is copied to attachments: `C:\Users\96152\.openclaw\workspace\attachments\Home-Cloud-Server\home-cloud-20260313-2347.png`.
