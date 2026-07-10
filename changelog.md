# Changelog

## Session 2026-07-10 — Phase 0 (Git & GitHub setup)

- `.gitignore` — added: standard Python/uv ignores, `.env`, logs, vector_db artifacts, IDE/OS files.
- `.github/workflows/ci.yml` — added: runs `uv sync`, `ruff check`, `pytest` on PRs and pushes to `main`.
- `.github/workflows/cd.yml` — added: builds and pushes a Docker image to GHCR on merge to `main` (tagged with commit SHA + `latest`). Depends on a `Dockerfile` that will be added in Phase 1.
- `README.md` — added: project overview and agent roster (Hermione, Rita, Percy, Moody).
- `changelog.md` — added: this file.
