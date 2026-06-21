# Project Guide — armada-ai

Contributor and release rules live in **[CONTRIBUTING.md](CONTRIBUTING.md)** — read it before opening a PR.

## Critical reminders for agents

- **Never push to `main`.** Releases to Test PyPI fire only when a PR is *merged* into `main` (`.github/workflows/release.yml`).
- **PR title must start with** `feat:` / `fix:` / `perf:` / `ci:` / `chore:` (lowercase, with colon) or no release runs. `docs:` does **not** trigger a release.
- **Bump `version` in `pyproject.toml`** in every releasable PR — Test PyPI rejects duplicate versions, and the failure is otherwise silent.

## Quality gates
```bash
ruff check armada_ai/
pytest --cov=armada_ai
```
