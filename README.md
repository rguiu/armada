# Armada

> Terminal orchestration for Open Code and Claude Code agents.

Manage multiple AI coding agents as a **hierarchy of tmux nodes** with a live dashboard. Orchestrator nodes spawn worker children, delegate tasks via API, monitor progress with per-step activity logs, and cascade-clean up — all through a local web UI.

## Architecture

SQLite (WAL mode) with FastAPI REST server, daemonized. Each node is a tmux window running an AI agent. Nodes report status via `POST /api/report`. The dashboard polls every 10 seconds with live status, activity logs, and multi-select batch operations.

## Features

- **Live tree dashboard** — dark themed, 10s auto-refresh, colour-coded node statuses
- **Agent types** — OpenCode, Claude Code, or Bash workers (parallel computation)
- **`/send` endpoint** — orchestrators assign tasks to workers via API, no raw tmux
- **`armada-work` tool** — wraps any command with automatic before/after status reporting
- **Pending status** — yellow pulsing badge when a node waits for user input/permission
- **Per-step activity logs** — agents report status before and after every action
- **Cascade kill & hide** — killing or deleting a parent also handles all descendants
- **Multi-select batch ops** — checkboxes in the tree for bulk kill/delete/attach
- **Plugin auto-reporting** — `tool.execute.before/after` hooks post pending on bash commands

## How It Works

```
┌──────────────────────────────────────────────────┐
│  Armada Dashboard (http://127.0.0.1:9100)         │
│  ┌─────────────┐  ┌─────────────────────────────┐│
│  │ Tree        │  │ Detail: "Architect"         ││
│  │             │  │ Status: active               ││
│  │ Architect ● │  │ Project: shipping-api        ││
│  │  ├─ Reviewer│  │ Message: "reviewing models"  ││
│  │  └─ Tests   │  │ [Attach] [Kill]              ││
│  │             │  │ Reports: ...                 ││
│  │ + Node      │  └─────────────────────────────┘│
│  │             │                                  │
│  │ Projects    │                                  │
│  │ shipping-api│                                  │
│  │ + Add       │                                  │
│  └─────────────┘                                  │
└──────────────────────────────────────────────────┘
         │
    ┌────┴────┐
    │  tmux   │
    │  armada  │
    │ session │
    └─────────┘
```

Each node is a tmux window running an AI agent (Open Code or Claude Code). Nodes can have a parent-child relationship forming a tree. Orchestrator nodes spawn children via the Armada API. The dashboard shows the full hierarchy with live status, recent activity, and logs.

## Installation

**Prerequisites:** Python 3.10+, tmux (`brew install tmux`), Open Code or Claude Code.

```bash
git clone https://github.com/rguiu/armada.git
cd armada
bash install.sh
```

That's it. `armada` is now available in your terminal. Open a new shell or run `source ~/.zshrc`.

<details>
<summary>Manual install (click to expand)</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
armada setup
echo 'export PATH="$PWD/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

</details>

## Quick Start

```bash
armada              # Start the server (daemon) + open dashboard
```

Open http://127.0.0.1:9100.

### Step 1: Register a project

In the sidebar **Projects** section, click **+ Add**. Give it an ID (slug), a name, and a directory path (or leave blank for the current directory).

### Step 2: Create a node

Click **+ Node**. Choose a name (or leave blank for auto-generated), select a project, pick an agent type (opencode / claude / bash).

### Step 3: Attach and work

Select the node in the tree and click **Attach**. This opens a terminal tab connected to the node's tmux window. The agent receives Armada status reporting instructions automatically.

### Step 4: Monitor

The dashboard polls every 10 seconds. You can see each node's current status, latest task, and full activity log. The tree shows parent-child relationships.

## Commands

| Command | Description |
|---|---|
| `armada` | Start daemon + open dashboard |
| `armada start` | Start daemon in background |
| `armada stop` | Stop the daemon |
| `armada attach` | Start in foreground (debugging) |
| `armada setup` | Install skills to user profile |

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/tree` | Full node hierarchy |
| `GET` | `/api/tree?hide_dead=true` | Live-only tree |
| `GET` | `/api/nodes` | Flat node list (includes dead) |
| `GET` | `/api/nodes?hide_dead=true` | Live-only node list |
| `POST` | `/api/nodes` | Create node |
| `DELETE` | `/api/nodes/:id` | Kill node + cascade children |
| `PATCH` | `/api/nodes/:id` | Hide node (`{"action":"hide"}`) — logical delete |
| `POST` | `/api/nodes/:id/send` | Send a command to a bash worker |
| `POST` | `/api/nodes/:id/attach` | Open terminal attached to node |
| `GET` | `/api/nodes/:id` | Node detail + reports |
| `GET` | `/api/nodes/:id/reports` | Node activity log |
| `POST` | `/api/report` | Agent status report (active/idle/error/pending) |
| `GET` | `/api/nodes/history` | Recently killed nodes |
| `GET/POST/DELETE` | `/api/project-labels` | CRUD project directories |

## Agent Skills

Armada ships with three skills that teach agents how to operate as managed nodes:

| Skill | Purpose |
|---|---|
| [`armada-node`](skills/armada-node/SKILL.md) | Full node: reports status, spawns/kills children, full orchestration |
| [`armada-worker`](skills/armada-worker/SKILL.md) | Leaf node: reports status, single-task focus |
| [`armada-orchestrator`](skills/armada-orchestrator/SKILL.md) | Orchestrator: spawns workers, delegates via /send, monitors |

Skills are installed to `~/.config/opencode/skills/` (OpenCode global) and `~/.claude/skills/` (Claude Code). They auto-activate when `ARMADA_NODE_NAME` is set in the environment.

### Installing Skills

```bash
armada setup
```

Copies skills and the pending-status plugin to `~/.config/opencode/`. Skills auto-activate when `ARMADA_NODE_NAME` is set in the environment (done automatically by Armada when creating a node).

This project's `opencode.json` also references `ARMADA.md` as an instruction file — kept project-local for the armada repo itself.

## Example: Multi-Agent Code Review Pipeline

Let's say you're building `shipping-api` in `/Users/you/projects/shipping-api`. You want three agents working in parallel:

```
Architect (orchestrator)
├── Reviewer (worker)  — reviews the code
└── Tests (worker)     — writes and runs tests
```

### Setup

```bash
# 1. Start Armada
armada

# 2. Register project
# In dashboard: Projects → + Add
#   ID: shipping-api
#   Name: Shipping API
#   Path: /Users/you/projects/shipping-api

# 3. Create orchestrator
# In dashboard: + Node
#   Name: Architect
#   Project: Shipping API
#   Agent: opencode

# 4. Skills already installed globally by 'armada setup' — no per-project copy needed.

# 5. Attach to Architect and start working
# Click Architect in tree → Attach
# The agent now has the armada-orchestrator skill loaded
```

### Architect's Workflow

The Architect (with `armada-orchestrator` skill) will:

1. Analyze the codebase structure
2. Spawn a `Reviewer` node for code review:
   ```bash
   curl -s -X POST http://127.0.0.1:9100/api/nodes \
     -H "Content-Type: application/json" \
     -d '{"name":"Reviewer","parent_id":1,"project_label_id":"shipping-api","agent_type":"opencode"}'
   ```
3. Spawn a `Tests` node for test writing
4. Monitor both via `GET /api/tree`
5. Collect results and kill workers when done

The dashboard shows the full tree updating in real time. Each worker reports "active" / "idle" as it works.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

### Running Tests

```bash
pytest                          # Run all tests
pytest --cov=armada_ai          # With coverage report
pytest -v tests/test_server.py  # Specific test file
```

### Linting

```bash
pip install ruff
ruff check armada_ai/ tests/
```

### CI Pipeline

On push/PR to `main`, GitHub Actions runs:
- **ruff** — code linting
- **pytest-cov** — test suite on Python 3.10–3.13 with 80% coverage threshold

## File Locations

| Path | Purpose |
|---|---|
| `~/.armada/armada.db` | SQLite database |
| `~/.armada/server.pid` | Daemon PID file |
| `~/.armada/hooks/<name>.md` | Per-node hook instructions |

## License

MIT
