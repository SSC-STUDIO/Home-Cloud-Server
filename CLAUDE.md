# Home Cloud Server

## Project Overview
Personal cloud storage server with file upload, download, preview, and management features.

## Tech Stack
- Language: Python
- Dependencies: requirements.txt, pyproject.toml
- Entry point: main.py
- Config: config.py
- Database: dev.db (SQLite)

## Development Rules
- Branch convention: work on `codex/ai-Home-Cloud-Server` branch
- Always update CHANGELOG.md and VERSION on releases
- Test with `python main.py` locally before committing
- Keep deploy/ scripts updated when changing server config

## Code Style
- Follow PEP 8
- Type hints encouraged
- Keep config.py as the single source of configuration

## Key Paths
- `app/` — application modules
- `deploy/` — deployment scripts
- `docs/` — documentation
- `config.py` — configuration
- `main.py` — entry point
