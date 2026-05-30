# Fleet — Architecture & Roadmap

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Fleet Dashboard (http://127.0.0.1:9100)         │
│  Dark-themed HTML, auto-refreshes every 10s      │
│  Tree sidebar + detail panel + actions           │
└────────────────────┬─────────────────────────────┘
                     │ HTTP (REST API)
┌────────────────────▼─────────────────────────────┐
│  Fleet Server (FastAPI, daemonized)              │
│  POST /api/report    ← agent hooks               │
│  GET  /api/tree      → dashboard tree            │
│  POST /api/nodes     ← create nodes              │
│  DELETE /api/nodes   ← kill nodes (cascade)      │
│  POST .../attach     ← open tmux terminal        │
│  CRUD /api/project-labels                        │
└────────────────────┬─────────────────────────────┘
                     │ sqlite3 / subprocess
┌────────────────────▼─────────────────────────────┐
│  fleet.db (SQLite, WAL mode)                     │
│  nodes | project_labels | status_reports         │
├──────────────────────────────────────────────────┤
│  Tmux session "fleet" (detached)                 │
│  Window 0: overview | Window N: <node-name>      │
│  Each window = one AI agent process              │
└──────────────────────────────────────────────────┘
```

## Database Schema

```sql
CREATE TABLE project_labels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE
);

CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    project_label_id TEXT REFERENCES project_labels(id),
    tmux_pane_id TEXT,
    colour TEXT NOT NULL,
    status TEXT DEFAULT 'idle',      -- 'idle' | 'active' | 'error' | 'dead'
    agent_type TEXT DEFAULT 'auto',  -- 'opencode' | 'claude' | 'bash'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    killed_at TEXT                   -- set when killed, NULL = alive
);

CREATE TABLE status_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    status TEXT NOT NULL,            -- 'active' | 'idle' | 'error'
    message TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## API Reference

| Method | Path | Body/Params | Response |
|---|---|---|---|
| `GET` | `/` | — | Dashboard HTML |
| `GET` | `/api/tree` | — | Nested node hierarchy |
| `GET` | `/api/nodes` | — | Flat node list |
| `GET` | `/api/nodes/:id` | — | Node detail + reports + children |
| `GET` | `/api/nodes/:id/reports` | `?limit=30` | Report history |
| `POST` | `/api/nodes` | `name, parent_id?, project_label_id?, agent_type` | Created node |
| `DELETE` | `/api/nodes/:id` | — | `{ok, killed}` |
| `POST` | `/api/nodes/:id/attach` | — | `{ok}` opens iTerm tab |
| `POST` | `/api/report` | `name, status, message` | `{ok}` |
| `GET` | `/api/project-labels` | — | List labels |
| `POST` | `/api/project-labels` | `id, name, path?` | `{ok}` |
| `DELETE` | `/api/project-labels/:id` | — | `{ok}` |

## Node Lifecycle

1. **Created** via dashboard or API → tmux window spawned, status `idle`
2. **Active** via agent hook → `POST /api/report` with `status: active`
3. **Idle** via agent hook → `POST /api/report` with `status: idle`
4. **Error** via agent hook → `POST /api/report` with `status: error`
5. **Dead** via dashboard kill / cascade / tmux window closed → health check marks dead

## Cascade Kill

Killing a parent node recursively marks all descendants as dead and kills their tmux windows. Implemented as iterative BFS on the `parent_id` tree.

## Health Check

Background thread every 15 seconds:
- Queries all active nodes
- Checks if their tmux window still exists
- If window is gone → marks node as dead (recursive cascade)

## Colours

12-colour palette assigned round-robin from active colours in DB. Ensures no two active nodes share the same colour.

## Naming

Default names from two pools:
- LOTR characters: Aragorn, Galadriel, Gimli, Legolas, Frodo, Samwise, Gandalf, etc.
- Adjective-noun pairs: misty-shield, silent-thunder, frozen-dawn, etc.

## Daemon

`fleet` (or `fleet start`) double-forks, writes PID to `~/.fleet/server.pid`. `fleet stop` reads PID file and sends SIGTERM.

## Roadmap

### Done (v0.1.0)
- [x] Tree hierarchy with cascade kill
- [x] Dashboard with sidebar tree + detail panel
- [x] Project label CRUD from dashboard
- [x] Agent skills (fleet-node, fleet-worker, fleet-orchestrator)
- [x] Agent hooks via HTTP POST to `/api/report`
- [x] Health check for dead tmux windows
- [x] Daemonize + PID file

### Next (v0.2.0)
- [ ] WebSocket for real-time dashboard updates (no polling)
- [ ] Node-to-node process piping (parent captures child stdout)
- [ ] Node auto-restart on crash
- [ ] Statistics / uptime charts

### Future (v0.3.0+)
- [ ] Multi-machine fleet (nodes on remote hosts)
- [ ] Authentication for remote dashboard access
- [ ] Configurable colour themes
- [ ] Cross-session search in logs
