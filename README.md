```
   █████╗ ██████╗ ███╗   ███╗ █████╗ ██████╗  █████╗
  ██╔══██╗██╔══██╗████╗ ████║██╔══██╗██╔══██╗██╔══██╗
  ███████║██████╔╝██╔████╔██║███████║██║  ██║███████║
  ██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║██║  ██║██╔══██║
  ██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║██████╔╝██║  ██║
  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝
```

> Command your fleet of AI agents from anywhere — your browser, your phone, your tablet.

[![PyPI](https://img.shields.io/pypi/v/armada-ai)](https://pypi.org/project/armada-ai/)
[![Test PyPI](https://img.shields.io/badge/testpypi-v0.2.1-blue.svg)](https://test.pypi.org/project/armada-ai/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://pypi.org/project/armada-ai/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/rguiu/armada/blob/main/LICENSE)

## What is Armada?

Armada runs [OpenCode](https://opencode.ai) and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) agents inside persistent tmux sessions, controlled from a web dashboard. Start an agent on your laptop, close it, and pick up where you left off — from any device on your network.

- **Web dashboard** — manage agents from any device
- **Persistent sessions** — agents survive browser closes, laptop sleeps, and server restarts
- **Orchestration** — agents spawn child nodes, delegate tasks, and run in parallel
- **One command** — `armada` starts the server and opens the dashboard

## Installation

**Prerequisites:** Python 3.10+, tmux, and either OpenCode or Claude Code installed on your PATH.

```bash
pip install armada-ai
armada setup                # install agent skills for OpenCode and Claude Code
```

`armada` is now available. You can also install from source or run via Docker — see below.

<details>
<summary>Docker</summary>

```bash
docker build -t armada .
docker run -d -p 9100:9100 --name armada armada
```
</details>

<details>
<summary>From source</summary>

```bash
git clone https://github.com/rguiu/armada.git
cd armada
bash install.sh
```
</details>

## Quick Start

```bash
armada                     # start server + open dashboard
```

Open `http://127.0.0.1:9100`.

1. **Register a project** — sidebar Projects → **+ Add**. Give it an ID, name, and directory path.
2. **Create a node** — click **+ Node**, pick a project, choose an agent type (OpenCode, Claude Code, or Bash), optionally add an initial prompt.
3. **Attach** — select the node and click **Attach**. Opens in iTerm2 (macOS) for full TUI, or in-browser via xterm.js.
4. **Monitor** — the dashboard updates every 10 seconds. See status, activity logs, and task history.
5. **Connect other devices** — scan the QR code in the sidebar to open the dashboard on your phone or tablet.

<video src="img/armada1.webm" autoplay loop muted playsinline width="100%"></video>

## Agent Types: Claude Code vs OpenCode

Armada supports both Claude Code and OpenCode as first-class agents. Each integrates differently:

### OpenCode

OpenCode is an open-source AI coding agent. Armada's OpenCode integration uses:

- **Plugin system** — an `armada-pending` plugin hooks into OpenCode's event loop (tool start/stop, permission requests, step completion). Agents automatically report `active`, `idle`, or `pending` status to Armada.
- **Skills** — `armada-node` and `armada-worker` skill files teach agents how to report status, spawn children, and send results.

To use OpenCode: install it, make sure `opencode` is on your PATH, and run `armada setup`. When creating a node, select "opencode" as the agent type.

### Claude Code

Claude Code is Anthropic's official CLI agent. Armada's Claude Code integration uses:

- **Hook system** — four shell hooks (`claude-pre-tool.sh`, `claude-post-tool.sh`, `claude-stop.sh`, `claude-permission.sh`) fire on tool use, idle transitions, and permission requests. These curl the Armada API to report status.
- **Skills** — the same skill files are installed to `~/.claude/skills/` and auto-activate when `ARMADA_NODE_NAME` is set.

To use Claude Code: install it via `npm install -g @anthropic-ai/claude-code`, make sure `claude` is on your PATH, and run `armada setup`. When creating a node, select "claude" as the agent type.

### Bash

Bare shell nodes without an agent. Useful for running scripts or manual commands. Armada provides a bash wrapper (`armada-bash.sh`) with functions like `armada_report_active`, `armada_spawn`, and `armada_kill_child`.

### Which one should you use?

| | OpenCode | Claude Code |
|---|---|---|
| **Install** | `pip install opencode` | `npm install -g @anthropic-ai/claude-code` |
| **Status reporting** | Plugin (TypeScript, event-driven) | Shell hooks (pre/post-tool, stop) |
| **Permissions** | Permission events in plugin | `claude-permission.sh` hook |
| **Cost tracking** | Token usage from step-finish events | Not built in |
| **Best for** | Open-source workflows, custom plugins | Anthropic ecosystem, official support |

Either works. Pick based on which agent you already have installed.

## Commands

| Command | Description |
|---|---|
| `armada` | Start daemon + open dashboard |
| `armada --no-browser` | Start server without opening browser |
| `armada start` | Start daemon in background |
| `armada stop` | Stop the daemon |
| `armada watch` | Interactive terminal dashboard (htop-style) |
| `armada create -p <project>` | Create a new agent node |
| `armada nodes` | List all agents in a table |
| `armada attach <name>` | Attach to a node by name (iTerm2) |
| `armada projects` | List projects |
| `armada projects add <id> <name> <path>` | Register a project |
| `armada projects rm <id>` | Remove a project |
| `armada setup` | Install skills to user profile |
| `armada version` | Print the Armada version |
| `armada token` | Print the auth token |
| `armada token --qr` | Print token as scannable QR code |
| `armada config` | Show or set configuration |
| `armada config set <key> <val>` | Change a config value (`default_agent`, `port`, etc.) |
| `armada service install` | Install as system service (launchd/systemd) |
| `armada status` | Show server health and agent counts |
| `armada doctor` | Clean up stale tmux sessions and DB state |
| `armada --lan` | Bind server to LAN IP (access from other devices) |

## CLI Watch Dashboard

`armada watch` is a live terminal dashboard for managing agents without a browser:

```
$ armada watch

 Nodes   Projects   |  3 active  1 pending  12 idle  |  23 agents

 ● HOOK20           ▣ idle   PGLease            unknown needs external_directory
 ○ HOOK18             idle   PGLease            server restarted — reconnected
 ○ H1                 idle   Armada
 ○ Armada-006         idle   Armada
 ● Armada-005         active Armada             running bash

 ⚠ Pending: HOOK20

 ┃ [↑↓]nav [enter]attach [n]ew [k]kill [d]delete [tab]projects [q]quit ┃
```

<details>
<summary>Full keybindings and forms</summary>

| Key | Action |
|---|---|
| `↑` `↓` | Navigate agent list |
| `Enter` | Attach to selected node (focuses existing pane) |
| `a` | Split-attach (experimental — opens a new tmux pane for the node) |
| `n` | New node (interactive form) |
| `k` | Kill selected node |
| `d` | Delete selected node |
| `Tab` | Switch to Projects view |
| `q` | Quit |

> **Note:** `a` (split-attach) is experimental and may not work reliably in all terminal environments. It is not shown in the bottom bar but remains available as a hidden shortcut.

Forms for creating nodes and projects use keyboard navigation: `Tab`/`↑↓` to move between fields, `←→` to cycle options, type freely in text fields, `Enter` on `[Save]` to submit, `Esc` to cancel.
</details>

## Multi-Agent Pipeline

```
Architect (orchestrator)
├── Reviewer (worker)  — reviews the code
└── Tests (worker)     — writes and runs tests
```

1. Start Armada: `armada`
2. Register a project and create an orchestrator node (agent type: "opencode" or "claude")
3. The orchestrator spawns child workers, delegates tasks, and monitors results
4. The dashboard updates in real time as each worker reports active/idle

Skills (`armada-node`, `armada-worker`, `armada-orchestrator`) teach agents how to spawn children, delegate work, and report results back to the dashboard.

## Architecture

SQLite (WAL) + FastAPI REST server, daemonized. Each node is a tmux session running an agent. Nodes report status via `POST /api/report`. The dashboard updates in real time over a persistent WebSocket.

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/tree` | Full node hierarchy |
| `POST` | `/api/nodes` | Create node |
| `GET` | `/api/nodes/:id` | Node detail + reports |
| `DELETE` | `/api/nodes/:id` | Kill node + cascades to children |
| `POST` | `/api/nodes/:id/send` | Send command to worker |
| `POST` | `/api/nodes/:id/attach` | Open terminal attached to node |
| `POST` | `/api/report` | Agent status report (`active`/`idle`/`pending`/`error`) |
| `GET/POST/DELETE` | `/api/project-labels` | CRUD project directories |
| `GET` | `/health` | Health check (no auth) |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/api/qr?url=` | SVG QR code |

Full API docs at `http://127.0.0.1:9100/docs` (FastAPI Swagger UI).

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"

pytest                          # run tests
pytest --cov=armada_ai          # with coverage
ruff check armada_ai/ tests/    # lint
```

CI runs ruff + pytest-cov on Python 3.10–3.13 on push to `main`.

## License

MIT
