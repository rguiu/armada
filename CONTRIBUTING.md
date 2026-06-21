# Contributing to armada-ai

Thanks for contributing! This guide covers how to get changes merged **and actually published to Test PyPI**. The release pipeline is title- and version-sensitive, so read the "Pull Requests" section before opening one.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

## Branch discipline

- Branch off the latest `main`; never commit directly to `main`.
- Use descriptive, prefixed branch names: `feat/`, `fix/`, `refactor/`, `chore/`, `docs/` (include an issue number when relevant, e.g. `feat/42-task-mailbox`).
- Keep each PR focused on one logical change.

## Pull Requests (so your change actually releases)

Releases to **Test PyPI** are driven by `.github/workflows/release.yml`, which runs **only when a PR is merged into `main`** and the **PR title** matches a trigger prefix.

### 1. Never push directly to `main`
`release.yml` triggers on `pull_request: closed` only. Commits pushed straight to `main` will **never** publish to Test PyPI. Always open a PR and merge it.

### 2. PR title MUST start with a release-triggering prefix
Use a lowercase conventional-commit prefix followed by a colon. An optional scope in parentheses is allowed.

Triggers a release:
- `feat: ...`   `feat(mcp): ...`
- `fix: ...`    `fix(cli): ...`
- `perf: ...`
- `ci: ...`
- `chore: ...`

Does **NOT** trigger a release (avoid for releasable changes):
- `docs: ...` — excluded from the trigger list
- `Feat/...`, `Fix/...` (branch-name style, capitalized, no colon) — does not match

> If a change is docs-only but you still want it published, either bump the version under a `chore:` PR or add `docs:` to the allowed prefixes in `release.yml`.

### 3. Bump the version in every releasable PR
Test PyPI **rejects re-uploads of an existing version**. Before merging, bump:

- `pyproject.toml` → `[project] version = "X.Y.Z"`

If the version is not bumped, the existing git tag is reused and the upload is rejected — the release job may still appear green even though nothing was published. Always increment the version. (`armada_ai/constants.py` reads the version automatically; no second edit needed.)

### 4. PR checklist before merge
- [ ] Branch created from latest `main`, not committed to `main` directly
- [ ] PR title starts with `feat:` / `fix:` / `perf:` / `ci:` / `chore:`
- [ ] `version` bumped in `pyproject.toml`
- [ ] `ruff check armada_ai/` passes
- [ ] `pytest` passes

## Quality gates

Run both before marking a change done:

```bash
ruff check armada_ai/
pytest --cov=armada_ai
```

## Releasing

- **Test PyPI** is automatic on merge (see above).
- **Production PyPI** is a manual, confirmed step: Actions → "Publish to Production PyPI" → enter `publish`.
- For the manual/local build-and-upload flow, see [`RELEASING.md`](RELEASING.md).
