```
   █████╗ ██████╗ ███╗   ███╗ █████╗ ██████╗  █████╗
  ██╔══██╗██╔══██╗████╗ ████║██╔══██╗██╔══██╗██╔══██╗
  ███████║██████╔╝██╔████╔██║███████║██║  ██║███████║
  ██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║██║  ██║██╔══██║
  ██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║██████╔╝██║  ██║
  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝
```

> Persistent sessions and live supervision for coding agents.

[![PyPI](https://img.shields.io/pypi/v/armada-ai)](https://pypi.org/project/armada-ai/)
[![Test PyPI](https://img.shields.io/badge/testpypi-v0.2.2-blue.svg)](https://test.pypi.org/project/armada-ai/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://pypi.org/project/armada-ai/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/rguiu/armada/blob/main/LICENSE)

## What is Armada?

Armada runs coding agents in persistent tmux sessions and lets you monitor and control them from a terminal dashboard or web UI.

Each agent runs in its own session and maintains state across reconnects, restarts, and devices.

## Key Features

- **Persistent agent sessions** — every agent runs inside a tmux session and survives disconnects
- **Live status tracking** — see `active`, `idle`, `pending`, `error` in real time
- **Terminal + web control** — manage agents via `armada nodes --watch` or the web dashboard
- **Multi-agent workflows** — spawn child workers, delegate tasks, coordinate execution
- **Message system** — structured communication between agents with event-driven delivery
- **MCP integration** — agents interact with Armada through typed tools, not curl commands

## Installation

**Prerequisites:** Python 3.10+, tmux, and either OpenCode or Claude Code installed on your PATH.

```bash
pip install armada-ai
armada setup                # install agent skills and MCP config
```

`armada` is now available. You can also install from source or run via Docker — see below.

<details>
<summary>Docker</summary>

```bash
docker build -t armada .
docker run -d -p 9100:9100 --name armada armada

# The container has its own token. Read it, then open the dashboard once with it:
docker exec armada armada token
# http://127.0.0.1:9100/?token=<token-from-above>
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
armada                     # start server + open dashboard with a one-time login ticket
```

If your browser opens automatically, you're done. Otherwise, with the server running:

```bash
armada token --qr          # prints a 60-second login URL and QR code
```

Open the printed link or scan the QR. The ticket logs you in once, sets an `HttpOnly` cookie for 7 days, and redirects to the dashboard. Opening `http://127.0.0.1:9100` without a ticket or cookie returns `401 Unauthorized` — this is intentional.

1. **Pick a project folder** — sidebar Projects → **+ Add** and enter a path (name defaults to the folder name). Or click **Scan** to find git repos under `project_roots` in `~/.armada/config.yaml`.
2. **Create a node** — click **+ Node**, pick a project, choose an agent type (OpenCode, Claude Code, or Bash), optionally add an initial prompt.
3. **Attach** — select the node and click **Attach**. Opens the agent session in iTerm2 (macOS) or in-browser via xterm.js.
4. **Monitor** — see status, activity logs, and task history in real time.
5. **Connect other devices** — start with `armada --lan`, then run `armada token --qr --lan` and scan the QR. Tickets expire after 60 seconds; rerun the command for a fresh one.

### Authentication

The dashboard and API are protected by a token stored in `~/.armada/token` (mode `0600`). The browser gets it through a one-time ticket and an `HttpOnly` cookie; API clients can send it directly:

```bash
curl -H "Authorization: Bearer $(armada token)" http://127.0.0.1:9100/api/tree
```

`/health` is the only public endpoint. To log in again after clearing cookies, run `armada token --qr`.

![Armada Dashboard](img/armada.png)

## CLI Dashboard

`armada nodes --watch` is a live terminal dashboard for managing agents without a browser:

```
$ armada nodes --watch

 Nodes   Projects   |  3 active  1 pending  12 idle  |  23 agents

 ● HOOK20           ▣ idle   PGLease            unknown needs external_directory
 ○ HOOK18             idle   PGLease            server restarted — reconnected
 ○ H1                 idle   Armada
 ○ Armada-006         idle   Armada
 ● Armada-005         active Armada             running bash

 ⚠ Pending: HOOK20

 ┃ [↑↓]nav [enter]attach [n]ew [k]kill [d]delete [tab]projects [q]quit ┃
```

![CLI Demo](img/armada1.gif)

<details>
<summary>Full keybindings and forms</summary>

| Key | Action |
|---|---|
| `↑` `↓` | Navigate agent list |
| `Enter` | Attach to selected node (focuses existing pane) |
| `a` | Split-attach (experimental) |
| `n` | New node (interactive form) |
| `k` | Kill selected node |
| `d` | Delete selected node |
| `Tab` | Switch to Projects view |
| `q` | Quit |

Forms for creating nodes and projects use keyboard navigation: `Tab`/`↑↓` to move between fields, `←→` to cycle options, type freely in text fields, `Enter` on `[Save]` to submit, `Esc` to cancel.
</details>

## Agent Types

Armada supports Claude Code, OpenCode, and Bash as agent types.

### OpenCode

- **MCP Server** — typed tools (`spawn_node`, `send_message`, `report_status`, etc.) directly in the agent's tool palette. Configured under `mcp.servers` in `opencode.json`.
- **Plugin system** — the `armada-pending` plugin uses OpenCode 2.x's V2 plugin API (`Plugin.define`). It is installed to `.opencode/plugins/` in a project or `~/.config/opencode/plugins/` globally, where OpenCode discovers it automatically.
- **Skills** — `armada-node` and `armada-worker` skill files teach agents orchestration and messaging patterns.

To use: install OpenCode from [opencode.ai](https://opencode.ai), make sure `opencode` is on your PATH, run `armada setup`.

### Claude Code

- **Hook system** — four shell hooks fire on tool use, idle transitions, and permission requests. These use the `armada report` CLI to report status.
- **Skills** — the same skill files are installed to `~/.claude/skills/` and auto-activate when `ARMADA_NODE_NAME` is set.

To use: install via `npm install -g @anthropic-ai/claude-code`, make sure `claude` is on your PATH, run `armada setup`.

### Bash

Bare shell nodes without an agent. Useful for running scripts or manual commands. Armada provides a bash wrapper with status reporting functions.

### Which one?

| | OpenCode | Claude Code |
|---|---|---|
| **Install** | install from [opencode.ai](https://opencode.ai) | `npm install -g @anthropic-ai/claude-code` |
| **Status reporting** | Plugin (TypeScript, V2 event hooks) | Shell hooks (pre/post-tool, stop) |
| **Permissions** | `permission.asked` / `permission.replied` events | `claude-permission.sh` hook |
| **Cost tracking** | Token/cost usage from `session.usage.updated` | Not built in |
| **Best for** | Open-source workflows, custom plugins | Anthropic ecosystem, official support |

Either works. Pick based on which agent you already have installed.

## Agent Delegation

Agents can delegate work to child nodes using MCP tools:

```
Orchestrator
├── Reviewer  — reviews the code
└── Tests     — writes and runs tests
                └── sends "job completed" message back to Orchestrator
```

1. Start Armada: `armada`
2. Register a project and create an orchestrator node
3. The orchestrator uses `spawn_node("reviewer")` and `send_task(node_id, "review the auth module")`
4. Workers send completion messages back via `send_message(to_node_id=parent_id, payload="job completed", msg_type="result")`
5. The orchestrator collects results via `read_inbox()` and cleans up with `kill_node()`

See [examples/](examples/) for tested workflows: parallel feature builds, multi-project security audits, work queues, and code review pipelines.

## MCP Server

Armada includes an MCP server that exposes operations as typed tools for AI agents:

| Tool | Purpose |
|------|---------|
| `spawn_node(name)` | Spawn a child node (inherits agent_type, project, parent) |
| `send_task(node_id, command)` | Send command to node (auto-waits for tmux init) |
| `kill_node(node_id)` | Kill node and descendants |
| `get_tree()` | Full node hierarchy with status |
| `report_status(status, message)` | Report own status |
| `send_message(to_node_id, payload)` | Send message to another node |
| `read_inbox()` | Read pending messages |
| `broadcast(payload)` | Send message to all children |
| `post_to_queue(payload)` | Post task to shared work queue |
| `claim_from_queue()` | Claim next available queue task |

Auto-configured when nodes are created. Run manually with `armada mcp`.

## Inter-Node Messaging

Nodes communicate through a task mailbox with event-driven delivery:

- **Direct messages** — any node can send structured messages to any other node
- **Broadcast** — fan-out a message to all children with one call
- **Work queue** — post tasks to a shared queue for any idle agent to claim
- **Event-driven delivery** — no polling; the server pushes messages via tmux when the recipient goes idle
- **Completion notifications** — workers notify their parent when a task is done

## Architecture

Armada uses a FastAPI server with SQLite (WAL). Each agent is backed by a tmux session — no custom agent runtime, just tmux providing persistence, reconnection, and multiplexing. Nodes report status via `POST /api/report`. The dashboard refreshes over a persistent WebSocket.

## Commands

`armada --help` lists every command, and `armada <command> --help` shows its options.
Global flags (`--lan`, `--qr`, `--no-browser`, `--keep-token`, `--foreground`)
can appear before or after the command.

| Command | Description |
|---|---|
| `armada` | Start the daemon and open the dashboard (default) |
| `armada start` | Start the server (`--foreground` to stay attached) |
| `armada stop` | Stop the daemon |
| `armada status [--json]` | Show server and fleet status |
| `armada nodes [--watch] [--all] [--json]` | List agents; `--watch` opens the live dashboard |
| `armada create [-p <path-or-id>] [-n name] [-a agent]` | Create a new agent node (default project: current directory) |
| `armada attach <name> [--split]` | Attach to a node by name |
| `armada restart <name-or-id>` | Kill and recreate a node |
| `armada logs <name> [-f] [-n 20]` | Tail a node's activity log |
| `armada projects [list\|scan\|add <path>\|rm]` | Manage project folders |
| `armada config [show\|init\|set]` | Show or edit `~/.armada/config.yaml` |
| `armada service install` | Install as a launchd/systemd service |
| `armada setup` | Install skills, hooks, and MCP config |
| `armada agents [--json]` | Show detected agent CLIs and versions |
| `armada mcp` | Start the MCP server (stdio mode) |
| `armada report <status> <msg>` | Report node status (used by agent hooks) |
| `armada doctor [--nuke]` | Clean up stale sessions and DB state |
| `armada token [--qr] [--lan]` | Print the raw auth token, or a one-time login link/QR (60s) |
| `armada demodb [seed\|path]` | Seed a demo database for recordings |
| `armada version` / `armada --version` | Print the Armada version |

Examples:

```bash
armada --lan --no-browser      # start on the LAN without opening a browser
armada token --qr --lan        # fresh 60s login link/QR for a phone or tablet
armada nodes --watch           # live terminal dashboard
armada nodes --all --json      # script-friendly agent list, including dead nodes
armada create -p ~/Projects/armada -a claude -m "review the auth module"
armada logs HOOK20 -f
```

Output is colourised automatically on a TTY. Use `--color` to force it, or `--no-color`
/ `NO_COLOR=1` to disable it. Commands that support `--json` are safe to pipe.


## API Endpoints

All `/api/*` routes and `/metrics` require `Authorization: Bearer $(armada token)` (browsers use the dashboard cookie). `/health` is public and minimal.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/tree` | Full node hierarchy |
| `POST` | `/api/nodes` | Create node |
| `GET` | `/api/nodes/:id` | Node detail + reports |
| `DELETE` | `/api/nodes/:id` | Kill node + cascades to children |
| `POST` | `/api/nodes/:id/send` | Send command to worker |
| `POST` | `/api/report` | Agent status report (token required) |
| `POST` | `/api/nodes/:id/messages` | Send message to node |
| `GET` | `/api/nodes/:id/messages` | Read node inbox |
| `PATCH` | `/api/messages/:id` | Acknowledge message |
| `POST` | `/api/nodes/:id/broadcast` | Broadcast to all children |
| `POST` | `/api/queue` | Post task to work queue |
| `GET` | `/api/queue` | List unclaimed tasks |
| `POST` | `/api/queue/:id/claim` | Claim a queue task |
| `GET/POST/DELETE` | `/api/project-labels` | List/register/remove project folders (`POST` accepts `{"path"}`) |
| `GET` | `/api/project-labels/discover` | Scan `project_roots` for unregistered projects |
| `GET` | `/api/pair-ticket` | Create a one-time dashboard login ticket |
| `GET` | `/health` | Public liveness check (`status`, `version`) |
| `GET` | `/metrics` | Prometheus metrics (token required) |

Full API docs at `http://127.0.0.1:9100/docs` (FastAPI Swagger UI). Endpoints will prompt for the bearer token.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"

pytest                          # run tests
pytest --cov=armada_ai          # with coverage
ruff check armada_ai/ tests/    # lint
```

CI runs ruff + pytest-cov on Python 3.10-3.13 on push to `main`.

## License

MIT
