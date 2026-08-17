# Endfield Logs website and API

This directory contains the public website, API, uploader, database models, and
shared upload packages.

## Components

- `apps/web`: Next.js rankings and battle-detail UI.
- `apps/api`: FastAPI authentication, upload, storage, and public APIs.
- `apps/uploader`: desktop upload workflow used by the unified client.
- `packages/parser_core`: local battle-log parsing and rDPS attribution.
- `packages/upload_domain`: shared upload models.
- `packages/uploader_core`: API client and payload-building helpers.

Production environment files, deployment configuration, databases, user logs,
game tables, and game images are intentionally excluded. Development uses
synthetic tests and a local SQLite database by default.

## Development

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm --dir apps/web dev
```

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` only for local overrides. Never commit production
values. See `../README.md` for repository-wide resource and security rules.

