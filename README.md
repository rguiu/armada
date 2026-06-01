# Armada

> Track, control, and reattach to AI coding agents running in persistent tmux sessions.

Armada gives you a live dashboard to manage OpenCode and Claude Code agents. Each agent runs in its own tmux window — attach anytime to see what it's doing, detach and let it keep working, and monitor status and activity from your browser. Kill, hide, or batch-operate on nodes from the UI. Orchestrator agents can spawn worker children, delegate tasks, and cascade-clean up.

## Installation

**Prerequisites:** Python 3.10+, tmux (`brew install tmux`), OpenCode or Claude Code.

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
armada              # Start the server + open dashboard
```

Open **http://127.0.0.1:9100**.

### 1. Register a project

In the sidebar **Projects** section, click **+ Add**. Give it an ID (slug), a name, and a directory path (or leave blank for the current directory).

### 2. Create a node

Click **+ Node**. Choose a name (or leave blank for auto-generated), select a project, pick an agent type — OpenCode, Claude Code, or Bash. Optionally provide an initial prompt.

### 3. Attach and work

Select the node and click **Attach**. A terminal tab opens connected to the node's tmux window. The agent starts in the project directory with Armada status reporting configured. Close the tab anytime — the agent keeps running. Reattach later to pick up where you left off.

### 4. Monitor

The dashboard polls every 10 seconds. See each node's current status, latest task, and full activity log.

## Commands

| Command | Description |
|---|---|
| `armada` | Start daemon + open dashboard |
| `armada start` | Start daemon in background |
| `armada stop` | Stop the daemon |
| `armada attach` | Start in foreground (debugging) |
| `armada setup` | Install skills to user profile |

## Example: Multi-Agent Pipeline

Three agents working on `shipping-api` in parallel:

```
Architect (orchestrator)
├── Reviewer (worker)  — reviews the code
└── Tests (worker)     — writes and runs tests
```

1. Start Armada: `armada`
2. In the dashboard, register the project (`shipping-api`) and create an orchestrator node
3. Attach to the orchestrator — it spawns workers, delegates tasks, and monitors results

The dashboard updates in real time as each worker reports active/idle.

## Features

- **Live tree dashboard** — dark theme, 10s auto-refresh, colour-coded status badges
- **Agent types** — OpenCode, Claude Code, or Bash workers
- **Initial prompts** — auto-type a prompt when a node starts
- **`/send` endpoint** — orchestrators assign tasks to workers via API
- **Pending status** — yellow pulsing badge when a node waits for input
- **Per-step activity logs** — agents report status before and after every action
- **Cascade kill & hide** — killing a parent also handles all descendants
- **Multi-select batch ops** — checkboxes in the tree for bulk kill/delete/attach

## Architecture

SQLite (WAL mode) + FastAPI REST server, daemonized. Each node is a tmux window running an agent. Nodes report status via `POST /api/report`. The dashboard polls every 10 seconds.

```
┌──────────────────────────────────────────────────┐
│  Armada Dashboard (http://127.0.0.1:9100)         │
│  ┌─────────────┐  ┌─────────────────────────────┐│
│  │ Tree        │  │ Detail: "Architect"         ││
│  │             │  │ Status: active               ││
│  │ Architect ● │  │ Project: shipping-api        ││
│  │  ├─ Reviewer│  │ Message: "reviewing models"  ││
│  │  └─ Tests   │  │ [Attach] [Kill]              ││
│  │ + Node      │  │ Reports: ...                 ││
│  │ Projects    │  └─────────────────────────────┘│
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

## Agent Skills

Armada ships with three skills that teach agents how to operate as managed nodes:

| Skill | Purpose |
|---|---|
| [`armada-node`](skills/armada-node/SKILL.md) | Full node: reports status, spawns/kills children |
| [`armada-worker`](skills/armada-worker/SKILL.md) | Leaf node: reports status, single-task focus |
| [`armada-orchestrator`](skills/armada-orchestrator/SKILL.md) | Orchestrator: spawns workers, delegates via /send |

Skills install to `~/.config/opencode/skills/` and `~/.claude/skills/`. They auto-activate when `ARMADA_NODE_NAME` is set in the environment.

```bash
armada setup
```

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/tree` | Full node hierarchy |
| `GET` | `/api/tree?hide_dead=true` | Live-only tree |
| `GET` | `/api/nodes` | Flat node list |
| `GET` | `/api/nodes?hide_dead=true` | Live-only node list |
| `POST` | `/api/nodes` | Create node |
| `GET` | `/api/nodes/:id` | Node detail + reports |
| `GET` | `/api/nodes/:id/reports` | Activity log |
| `GET` | `/api/nodes/history` | Recently killed nodes |
| `DELETE` | `/api/nodes/:id` | Kill node + cascade |
| `PATCH` | `/api/nodes/:id` | Hide node (`{"action":"hide"}`) |
| `POST` | `/api/nodes/:id/send` | Send command to worker |
| `POST` | `/api/nodes/:id/attach` | Open terminal attached to node |
| `POST` | `/api/report` | Agent status report |
| `GET/POST/DELETE` | `/api/project-labels` | CRUD project directories |

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

### Tests

```bash
pytest                          # Run all tests
pytest --cov=armada_ai          # With coverage report
```

### Lint

```bash
pip install ruff
ruff check armada_ai/ tests/
```

### CI

On push/PR to `main`, GitHub Actions runs **ruff** + **pytest-cov** on Python 3.10–3.13 (80% coverage threshold).

## License

MIT
