# Changelog
All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

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
