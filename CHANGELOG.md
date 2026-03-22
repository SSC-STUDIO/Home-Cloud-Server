# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

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
