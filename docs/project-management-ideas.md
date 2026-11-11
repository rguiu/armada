# Simplifying Project Management

Notes from reviewing the `feat/opencode-v2-plugin` branch. No code changed yet — this is the options list.

## What exists today

A "project" is a triple `(id, name, path)`, created by hand, with **three places of truth**:

| Layer | Where | Notes |
|---|---|---|
| SQLite `project_labels` | `armada_ai/infrastructure/database.py:78` | real source of truth, `path` is already `UNIQUE` |
| `~/.armada/projects.json` | `armada_ai/infrastructure/db_projects.py:60-98` | rewritten on every add/delete, read back on startup |
| `config.yaml → projects: []` | `armada_ai/config.py:14` (`DEFAULTS`) | declared but **never read anywhere** |

### UX friction

- CLI: `armada projects add <id> <name> <path>` — three arguments, two of which are derivable (`armada_ai/cli.py:368`, `cli.py:1717`).
- API: `POST /api/project-labels` rejects unless both `id` and `name` are sent (`armada_ai/server.py:962`).
- Web: separate ID / Name / Path form (`armada_ai/templates/index.html:715`).
- Node creation **requires** a pre-registered project (`server.py:470`) and `-p` is required in the CLI (`cli.py:344`). So `cd my-repo && armada create` fails even though the answer is obvious.
- `id` is purely internal — nothing human-facing depends on it, and `path` is already unique.

The registry is also redundant with the filesystem: the overview endpoint already scans the folder for skills, plugins, hooks and git info. The only real job of the table is grouping nodes.

## Ideas, smallest → boldest

### 1. Make path the only required input (highest value / lowest risk)

- `armada projects add ~/Projects/foo` → derive `id` (slug) and `name` (basename); allow `--name` to override.
- `POST /api/project-labels` accepts `{path}`; fill missing `id`/`name` server-side.
- `armada create` with no `-p` defaults to `cwd`; if the path isn't registered, auto-register it.
- Web "Add project" becomes one folder field; name pre-filled from the basename.
- Removes the "A project must be selected" dead end without schema changes.

### 2. Discover projects from configured roots

- Add `project_roots: [~/Projects, ~/work]` to `config.yaml` (replacing the dead `projects: []` key).
- On demand (`armada projects scan`, dashboard Refresh), walk each root (default depth ~2) and mark folders containing any of `.git`, `.opencode`, `.claude`, `opencode.json`, `package.json`, `pyproject.toml`.
- Sidebar shows **Discovered** vs **Added**; clicking a discovered one registers it. Optional "auto-register on first node".
- Zero setup for most users; no more maintaining a list by hand.

### 3. Delete the JSON sidecar

- SQLite only; keep a one-time import of an existing `projects.json`, then stop writing it.
- Removes `_save_projects_to_json`, `sync_projects_from_json`, the startup hook, and the drift/staleness class of bugs (roughly most of `db_projects.py` and its call sites).
- Also drop the unused `projects` key from `config.DEFAULTS`.

### 4. Remove projects entirely (most radical)

- Add `nodes.workspace_path`; group the tree by directory; no `project_labels` table.
- Simplest mental model: *a project is a folder a node runs in.*
- But it breaks `/api/project-labels`, the MCP `list_projects` tool, extensions "installed in", and needs a data migration. Only worth it if a v2 API break is acceptable.

## Recommendation

Combine **1 + 2**: *a project is a folder; discovered automatically, registered when used.*

- `armada create` in a repo just works; `-p` becomes `-p <path-or-id>` and is optional.
- Manual registration is one argument, and only when you want it.
- Discovery makes onboarding "start Armada and pick a folder".
- The JSON sidecar stays for now (see below).

This is additive and backward-compatible — old `id`-based calls keep working, so UI/tests can migrate incrementally.

## Decisions

| Idea | Decision |
|---|---|
| 1. Path-only input | **Implemented.** `POST /api/project-labels` accepts `{"path"}` and derives `id`/`name`; `armada projects add <path>`; `armada create` defaults to `cwd`; node creation accepts `project_path` and auto-registers. |
| 2. Discovery from roots | **Implemented.** `project_roots` in `config.yaml`, `GET /api/project-labels/discover`, `armada projects scan`, dashboard **Scan**. |
| 3. Delete JSON sidecar | **Keep.** It is useful for sharing one project list across environments (e.g. separate `ARMADA_DB_PATH` databases). See notes below. |
| 4. Remove projects entirely | **No.** Re-adding a path for every node would be tedious. |

## Notes on the JSON sidecar (idea 3)

Today `~/.armada/projects.json` is a mirror of `project_labels`: loaded into the DB at startup and rewritten on every add/delete. That gives one shared project catalog even when you point different environments at different databases with `ARMADA_DB_PATH` (the JSON path does not change with the DB).

Options if it becomes a problem:

- **Keep as-is** (shared catalog across environments).
- **Add `ARMADA_PROJECTS_FILE`** (2 lines in `constants.py`) so an environment can opt into its own list while the default stays shared.
- **Derive the file from the DB path** (`ARMADA_DB_PATH=~/env.db` → `~/env-projects.json`). Clean per-environment isolation, but loses the shared catalog.
- **Explicit `armada projects export/import`** instead of a mirror. Most flexible, most code.

Recommendation: keep the mirror, add the env override only if environment isolation is needed.

## Open decision

**Compatibility**: the path-only API is additive; `id`/`name` are still accepted for old clients. Say if you want a breaking path-only API instead.

## Done in this change

- Path-only registration and `cwd` default in CLI, HTTP API, and dashboard.
- Folder discovery via `project_roots`, `armada projects scan`, and the dashboard **Scan** button.
- Backward compatibility: `POST /api/project-labels` still accepts `id`/`name` (and defaults the path to the server's cwd). The CLI form is now path-first.
