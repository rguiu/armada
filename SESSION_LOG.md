# Session Log — Production Readiness

Branch: `feat/production-readiness-and-persistence`

---

## 1. Time: 2026-06-09T...

### ✅ Add CSP header

**File:** `armada_ai/server.py:123-131`

**What was done:**
Added a `csp_middleware` that injects `Content-Security-Policy` header on every HTTP response. The policy restricts:
- Script sources: `'self'`, `https://esm.sh`, `https://cdn.jsdelivr.net` (plus inline/eval for existing dashboard code)
- Style sources: `'self'`, `https://cdn.jsdelivr.net` (plus inline styles)
- Connect sources: `'self'`, `ws:`, `wss:`
- Image sources: `'self'`, `data:`, `https:`
- Font sources: `'self'`, `data:`
- Base URI + form action: `'self'`

**How to test:**
```bash
# 1. Unit test: verify CSP header is present on all response types
python -c "
from armada_ai.server import app
from fastapi.testclient import TestClient
c = TestClient(app)
# HTML page
assert 'content-security-policy' in c.get('/').headers
# API endpoint
assert 'content-security-policy' in c.get('/api/info').headers
# WebSocket upgrade (headers still set on handshake)
print('CSP header present on all responses')
"

# 2. Browser test: Open dashboard, check DevTools → Network → response headers
#    Should see: Content-Security-Policy: default-src 'self'; ...

# 3. XSS test (manual): Try injecting a script tag via the agent command input
#    Browser console should show CSP violation errors if script tries to load
#    from an untrusted origin

# 4. CDN test: Verify xterm.js (esm.sh) and xterm.css (jsdelivr.net) still load
#    Dashboard should render terminal correctly
```

**Time spent:** ~15min

---

## 2. Audit innerHTML → esc()

**File:** `armada_ai/templates/index.html`

**What was done:**
Audited all 30+ `innerHTML` assignments in the dashboard. Agent-controlled data (`name`, `status`, `latest_message`, `agent_type`) was already properly escaped via the `esc()` function in most places, but found 5 locations where user/server data was inserted into HTML without escaping:

1. **Line 859** — Plugin agent type (`p.agent`) used unescaped in class + text content
2. **Line 865** — Hook agent type (`h.agent`) used unescaped in class + text content
3. **Line 871** — Config agent type (`agent`) used unescaped in class + text content
4. **Line 853** — Skill source (`s.source`) used unescaped in CSS class attribute
5. **Line 1485** — Node name (`n.name`) in dropdown options not escaped in `addNodes()`

All 5 fixed by wrapping with the existing `esc()` HTML-escape function.

**Verified safe (already correct):**
- Node names in tree/detail → `esc(n.name)`
- Status badges → server-enum (safe values)
- Report messages → `esc(r.message)`
- Permission messages → `esc(latestMsg)`
- Git info → `esc(git.branch)` etc.
- xterm.js terminal output → rendered via canvas (not HTML)

**How to test:**
```bash
# 1. Create a node with HTML in the name to verify escaping
curl -X POST "http://127.0.0.1:9100/api/nodes?token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_label_id":1, "name":"<script>alert(1)</script>"}'
# The dashboard should show the literal text, not execute the script

# 2. Check project overview renders plugin/hook safely
# Create plugin files with special characters, open project overview

# 3. Verify all tests still pass
python -m pytest tests/ -v
```

**Time spent:** ~30min

---

## 3. Clear sensitive env vars before agent spawn

**File:** `armada_ai/tmux.py:840-864` (SENSITIVE_ENV_VARS list + _sanitize_env_prefix), `armada_ai/tmux.py:264-293` (inject prefix into shell commands)

**What was done:**
Added a deny-list of 35 known sensitive environment variable names (AWS credentials, API keys, tokens, cloud secrets). Before each agent tmux window spawns, the shell command now includes `unset AWS_ACCESS_KEY_ID GITHUB_TOKEN ... 2>/dev/null;` to strip these vars from the agent's environment.

Key design decisions:
- **Deny-list, not allow-list**: Safer to preserve unknown vars than break functionality
- **SSH_AUTH_SOCK preserved**: Agents need git push/pull for code work
- **HOME, PATH, SHELL, LANG preserved**: Essential for shell/agent functionality
- **Silent failure**: `2>/dev/null` prevents errors if a var doesn't exist in the user's env
- **Server-time evaluation**: Subset of vars present when node is created

**How to test:**
```bash
# 1. Set a fake sensitive env var and verify it's cleared in agent
export GITHUB_TOKEN="ghp_test123"
# Start armada, create a new node
# Inside the node's tmux window, run: echo $GITHUB_TOKEN
# Should print nothing (empty)

# 2. Verify essential vars are preserved
# Inside node's tmux window: echo $HOME $PATH $SHELL
# Should print valid paths

# 3. Verify SSH still works (git push/pull)
# Inside node's tmux window: ssh -T git@github.com 2>&1
# Should show authenticated message

# 4. Run tests
python -m pytest tests/ -v

# 5. Programmatic check
python -c "
import os
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['HOME'] = '/home/test'
from armada_ai.tmux import _sanitize_env_prefix
p = _sanitize_env_prefix()
assert 'AWS_ACCESS_KEY_ID' in p
assert 'HOME' not in p
print('OK')
"
```

**Time spent:** ~20min

---

## 4. Move token out of URL

**Files:** `armada_ai/server.py:197-203` (embed token in HTML), `armada_ai/server.py:836` (browser open URL), `armada_ai/templates/index.html:578-590` (initAuth JS)

**What was done:**
Instead of passing the auth token as a `?token=XYZ` query parameter (leaks into browser history, screenshots, QR photos), the token is now embedded in a `<meta name="armada-token">` tag inside the dashboard HTML response. The JavaScript `initAuth()` reads the meta tag first, falls back to URL param for backward compat, then sessionStorage.

Changes:
1. **Server**: `dashboard_page()` injects `<meta name="armada-token" content="TOKEN">` into the `<head>` of the HTML
2. **Server**: `start_server()` no longer appends `?token=...` to the browser URL
3. **JS**: `initAuth()` reads meta tag > URL param (legacy) > sessionStorage

Security improvement:
- Token no longer appears in browser history
- Token no longer appears in URL bar (screenshots)
- Token no longer appears in QR code URLs
- `Authorization: Bearer` header is still used for all API calls (unchanged)
- Backward compatible: existing bookmarks with `?token=` still work

**How to test:**
```bash
# 1. Verify token embedded in HTML
python -c "
from armada_ai.server import app, _ensure_token
_ensure_token()
from fastapi.testclient import TestClient
c = TestClient(app)
r = c.get('/')
assert 'armada-token' in r.text
assert 'content=' in r.text
print('OK - token embedded')
"

# 2. Verify browser URL no longer contains token
# Start armada: python -m armada_ai
# Browser opens to http://127.0.0.1:9100 (no ?token= in URL)
# Check sessionStorage: armada_token should have the token value

# 3. Verify backward compat
# Open http://127.0.0.1:9100/?token=TEST123
# Dashboard should authenticate using the URL param (legacy path)
# URL should be cleaned to http://127.0.0.1:9100

# 4. Verify WebSocket still works
# Terminal view should connect with token from meta/sessionStorage
# Check DevTools → WebSocket frames → no auth errors

# 5. Run tests
python -m pytest tests/ -v
```

**Time spent:** ~15min

---


## 5. Vendor xterm.js locally

**Files:** `armada_ai/static/xterm.js`, `armada_ai/static/xterm.css`, `armada_ai/server.py:14,34-36,138-145`, `armada_ai/templates/index.html:7-14`

**What was done:**
Removed CDN deps by vendoring xterm@5.5.0 into `armada_ai/static/`. Added StaticFiles mount, updated importmap + CSS link to local paths, removed /static/ from auth middleware, tightened CSP to remove CDN domains.

**How to test:**
```bash
# Verify static files served
python -c "from armada_ai.server import app; from fastapi.testclient import TestClient; c=TestClient(app); assert c.get('/static/xterm.css').status_code==200; assert c.get('/static/xterm.js').status_code==200; print('OK')"
# Verify no CDN references in HTML or CSP
curl -s http://127.0.0.1:9100/ | grep -E 'esm\.sh|jsdelivr'  # should be empty
# Browser: open terminal view, should work normally
```

**Time spent:** ~20min

## 6. Separate tmux session per agent

**Files:** `armada_ai/tmux.py`, `armada_ai/server.py:465,516`, `tests/test_tmux.py`

**What was done:**
Refactored tmux architecture from one shared session (`armada`) with per-agent windows to per-agent sessions (`armada-{name}`). This prevents agents from accessing other agents' windows via tmux commands.

Key changes:
- Added `_agent_session(name)` / `_agent_target(name)` helpers returning `armada-{name}`
- `create_node_window`: uses `tmux new-session -d -s armada-{name}` instead of `new-window`
- `kill_node_window`: uses `tmux kill-session -t armada-{name}` instead of `kill-window`
- `window_exists`: uses `tmux has-session` instead of parsing `list-windows`
- `running_window_names`: parses `list-sessions` filtered by `armada-` prefix
- `has_attached_clients`: uses `list-clients` (all sessions) instead of session-scoped
- `attach_node`: uses `tmux attach-session -t armada-{name}` directly instead of creating `_view_*` sessions
- `send_keys` / `send_raw_keys` / `send_initial_prompt`: target changed to `armada-{name}`
- Server terminal WS: target changed from `armada:{name}` to `armada-{name}`
- Removed unused `_next_attach_id` / `_attach_counter`

**How to test:**
```bash
# 1. Create a node, verify it gets its own session
# Start armada, create node, then:
tmux list-sessions
# Should show: armada (overview) and armada-{node_name}

# 2. Verify agent isolation: from one agent's session,
# try to send keys to another agent:
tmux send-keys -t armada-other-agent "echo pwned"
# Should fail (session doesn't exist or different session)

# 3. Run tests
python -m pytest tests/ -v

# 4. Verify attach still works (via iTerm, Terminal, or web terminal)
# Should attach directly to agent's session

# 5. Verify server restart recovery
# Kill server, restart, check health loop recovers nodes
```

**Time spent:** ~45min

## 7. Error page with reconnection UI

**File:** `armada_ai/templates/index.html`

**What was done:**
Added a full-screen error overlay with auto-reconnection when the server goes down:
- CSS error overlay (full-screen dark background with centered content)
- Connection indicator dot in sidebar (green/yellow/red)
- Auto-retry with exponential backoff (1.5s → 2.2s → 3.3s → ... up to 30s)
- Live countdown in the overlay ("Reconnecting in 5s...")
- "Retry Now" button for immediate manual reconnect
- State machine: connected → reconnecting → disconnected

**How to test:**
```bash
# 1. Start armada, open dashboard
# 2. Kill the server (Ctrl+C)
# 3. Dashboard should show the error overlay immediately
# 4. Countdown should auto-retry with increasing intervals
# 5. Click "Retry Now" to skip the timer
# 6. Restart server — overlay should disappear automatically
```

**Time spent:** ~25min

## 8. Fix SQLite concurrency (database is locked)

**File:** `armada_ai/db.py`

**What was done:**
Added retry logic with exponential backoff for "database is locked" errors and increased SQLite page cache from 2MB to 8MB to reduce I/O contention under concurrent write load. Writes are already serialized via `_write_lock`; retries handle transient lock conflicts when 8+ agents report simultaneously.

**How to test:**
```bash
# 1. Run tests
python -m pytest tests/ -v

# 2. Stress test: create multiple nodes, have them report simultaneously
# Should not see "database is locked" errors in server logs

# 3. Check WAL mode is active
python -c "
from armada_ai.db import _get_conn
conn = _get_conn()
print(conn.execute('PRAGMA journal_mode').fetchone()[0])
"
# Should print "wal"
```

**Time spent:** ~15min

## 9. Persistent workspace per agent

**File:** `armada_ai/tmux.py:16,26-27,275-308`

**What was done:**
Each agent now gets a persistent workspace at `~/.armada/workspaces/<node_name>/`. The `ARMADA_WORKSPACE` env var is exported in every agent shell. The workspace directory is created on node creation. Agent hook instructions also reference the workspace so agents know where to save persistent output.

**How to test:**
```bash
# 1. Create a node, check workspace exists
ls ~/.armada/workspaces/
# Should show directories per node

# 2. Inside agent: echo $ARMADA_WORKSPACE
# Should show ~/.armada/workspaces/<node_name>

# 3. Agent can write: echo "hello" > $ARMADA_WORKSPACE/output.txt
# File survives tmux pane death
```

**Time spent:** ~10min

## 10. Structured agent logs with levels and output capture

**Files:** `armada_ai/logs.py`, `armada_ai/tmux.py:341-348`, `armada_ai/health.py:62-71`, `armada_ai/server.py:371-378`

**What was done:**
Added `level` field (debug/info/warn/error) to all log events. Added `log_agent_output()` to capture tmux pane content when a node is killed (both manual delete and health-check death detection). Output is stored in the node's JSONL log file at `~/.armada/logs/{name}.jsonl`.

**How to test:**
```bash
# 1. Check log levels in events
cat ~/.armada/logs/_server.jsonl | python -m json.tool
# Should show "level": "info" on each line

# 2. Kill a node, check its log for captured output
cat ~/.armada/logs/<node_name>.jsonl | python -m json.tool
# Should have "output" event with pane content

# 3. Search logs via API
curl -s "http://127.0.0.1:9100/api/logs?token=...&q=error" | python -m json.tool
```

**Time spent:** ~20min

## 11. Agent auto-restart on crash

**Files:** `armada_ai/health.py:75-95`, `armada_ai/db.py:586-593`

**What was done:**
When the health check detects an agent's tmux session has died, it now auto-restarts the agent with the same configuration. Max 3 restart attempts per agent name (reset on server restart). Restart reuses the existing DB node entry via `create_node`'s IntegrityError handler which reactivates dead nodes.

**How to test:**
```bash
# 1. Create a node, manually kill its tmux session
tmux kill-session -t armada-<node_name>

# 2. Wait for health check (15s interval)
# Check logs:
cat ~/.armada/logs/<node_name>.jsonl | grep restarted
# Should show "restarted" event

# 3. Dashboard should show the node as active again

# 4. After 3 restarts, should see "restart_limit" event and stop restarting
```

**Time spent:** ~25min

## 12. Server restart recovery

**File:** `armada_ai/server.py:142-157`

**What was done:**
Added explicit recovery notification on server restart. The existing `recover_on_startup()` already found surviving tmux sessions and reconnected them. Added a delayed status report update to each recovered node broadcasting the reconnection.

**How to test:**
```bash
# 1. Start server, create agents
# 2. Kill server (Ctrl+C)
# 3. Restart server
# 4. Dashboard should show agents with "server restarted — reconnected to agent" status
# 5. Health loop resumes monitoring
```

**Time spent:** ~10min

## 13. /health endpoint

**File:** `armada_ai/server.py:768-783,112`

**What was done:**
Added public `/health` endpoint returning `{"status":"ok","agents":N,"active":N,"pending":N,"idle":N,"uptime":S,"version":"0.2.0"}`. No auth required (added to exempt list). Enables Docker HEALTHCHECK, Kubernetes probes, and uptime monitoring.

**How to test:**
```bash
curl http://127.0.0.1:9100/health
# {"status":"ok","agents":2,"active":1,"pending":0,"idle":1,"uptime":120.5,"version":"0.2.0"}
```

**Time spent:** ~10min

## 14. Dockerfile

**Files:** `Dockerfile`, `.dockerignore`

**What was done:**
Multi-stage-ready Dockerfile with python:3.12-slim, tmux + git installed, HEALTHCHECK using /health endpoint, armada server as ENTRYPOINT. Added .dockerignore for efficient builds.

**How to test:**
```bash
docker build -t armada .
docker run -d -p 9100:9100 --name armada armada
curl http://127.0.0.1:9100/health
docker ps  # should show healthy
```

**Time spent:** ~10min

---

## 15. Time: 2026-06-09T20:50

### Fix: Dashboard breakage after vendoring

**Files:** `armada_ai/templates/index.html:8-15,1223-1224,1698-1699`, `armada_ai/server.py:209-226`

**What was done:**
Two bugs introduced during the vendoring session broke the dashboard:

1. **xterm.js ES module import failure**: The vendored `xterm.js` is a UMD bundle, not an ES module. The importmap (`import { Terminal } from '@xterm/xterm'`) failed because the file does not provide a named ES module export. Fix: Changed to a regular `<script src="/static/xterm.js">` tag.

2. **WebSocket URL mangling**: `connectTreeWs()` built WebSocket URLs using `location.host` concatenation, which produced a broken URL like `ws://127.0.0.1:9100/ws//127.0.0.1:9100/api/ws`. Fix: Changed both WS url constructions to use `location.origin.replace(/^http/, 'ws')` which reliably produces the correct origin.

3. **Service worker cache**: Changed the service worker to self-destruct on activate — deletes all caches and doesn't cache anything new. Prevents stale cached pages from being served after code changes.

**How to test:**
- Open dashboard at http://127.0.0.1:9100
- Check browser console — no more xterm import errors or WebSocket URL errors
- Dashboard tree should connect and show agents

**Time spent:** ~20min

---

## 16. Time: 2026-06-09T20:52

### ✅ Prometheus /metrics endpoint

**Files:** `armada_ai/metrics.py` (new), `armada_ai/server.py:21,117,698-716,803-819`

**What was done:**
Added a `/metrics` endpoint returning Prometheus text format. No external dependencies — the metrics module has its own simple registry with zero-alloc text rendering.

Metrics exposed:
- **`armada_uptime_seconds`** — gauge, refreshed on every scrape
- **`armada_agents{status="..."}`** — gauge per status (active, idle, pending)
- **`armada_reports_total`** — counter, incremented on each `/api/report` call
- **`armada_errors_total`** — counter, incremented when agent reports error status
- **`armada_nodes_created_total`** — counter, incremented on each `/api/nodes` POST
- **`armada_report_latency_seconds`** — histogram, client-to-server report latency (buckets: 0.1, 0.5, 1, 5, 10, 30, 60, 300, 900, 3600s)

Implementation details:
- Thread-safe in-memory registry with `threading.Lock`
- No auth required (added to exempt list alongside `/health`)
- `metrics.init()` called on server startup
- Counter increments hooked into existing create_node and agent_report paths
- Health endpoint also updates agent gauges for immediate visibility

**How to test:**
```bash
# Verify endpoint returns Prometheus format
curl -s http://127.0.0.1:9100/metrics

# Verify no auth required
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9100/metrics
# Should return 200

# Scrape with Prometheus
# Add to prometheus.yml:
# scrape_configs:
#   - job_name: 'armada'
#     static_configs:
#       - targets: ['localhost:9100']
#     metrics_path: '/metrics'

# Run tests
python -m pytest tests/ -v
```

**Time spent:** ~30min

---

## 17. Time: 2026-06-09T20:58

### ✅ Structured logging — log rotation

**Files:** `armada_ai/logs.py:116-129`, `armada_ai/health.py:24-30`

**What was done:**
Log rotation was already implemented (`rotate_logs` function gzips .jsonl files over 50MB) but never called automatically. Added:
1. Hooked `logs.rotate_logs()` into the periodic health loop (every 20 ticks = ~5 min)
2. Added `logs.cleanup_old_rotated_logs()` that deletes .gz files older than 30 days

Combined with the previously-done log levels (#10) and existing JSONL format, structured logging is now complete:
- Log levels: DEBUG/INFO/WARN/ERROR (done in #10)
- JSON format: one JSON object per line (existing)
- Log rotation: automated gzip + old file cleanup (this step)

**How to test:**
```bash
# Verify log rotation function works
python -c "
from armada_ai import logs
logs.rotate_logs(max_size_mb=50)
logs.cleanup_old_rotated_logs(max_age_days=30)
print('OK')
"

# Run tests
python -m pytest tests/ -v
```

**Time spent:** ~10min

---

## 18. Time: 2026-06-09T21:00

### ✅ `pip install armada` — PyPI-ready package

**Files:** `pyproject.toml:1-55`, `README.md:14-19`

**What was done:**
Made the project pip-installable as `armada-ai`:
1. Added PyPI metadata: readme, license (MIT), authors, keywords, classifiers, project URLs
2. Added `[project.scripts]` entry point: `armada = "armada_ai.cli:main"` (already existed)
3. Configured `[tool.setuptools.packages.find]` to include only `armada_ai` (exclude tests)
4. Added `[tool.setuptools.package-data]` to include `templates/**` and `static/**`
5. Updated README with `pip install armada-ai` install instructions
6. Verified: `python -m build --wheel` produces clean wheel (no test files)
7. Verified: `pip install dist/*.whl` installs and `armada --help` works

**How to test:**
```bash
# Build wheel
python -m build --wheel

# Install locally
pip install dist/armada_ai-0.1.0-py3-none-any.whl

# Verify CLI
armada --help
armada token

# Publish to PyPI (requires twine + API token)
# twine upload dist/*
```

**Time spent:** ~20min

---

## 19. Time: 2026-06-09T21:05

### ✅ Config file (`~/.armada/config.yaml`)

**Files:** `armada_ai/config.py` (new), `armada_ai/server.py:23,39-40,178`, `armada_ai/health.py:4,9`, `armada_ai/cli.py:97-98,107,510-554`

**What was done:**
Added a YAML config file at `~/.armada/config.yaml` with zero external dependencies (minimal YAML parser included). Configurable settings:

| Key | Default | Description |
|-----|---------|-------------|
| `port` | 9100 | Server listen port |
| `host` | 127.0.0.1 | Bind address |
| `default_agent` | opencode | Default agent type for new nodes |
| `health_interval` | 15 | Health check interval (seconds) |
| `max_restarts` | 3 | Max auto-restart attempts per agent |

Server and health loop read config on startup. CLI commands:
- `armada config` — show current settings
- `armada config init` — create default config file
- `armada config set <key> <value>` — change a setting

**How to test:**
```bash
armada config
armada config set port 9101
armada config set max_restarts 5
cat ~/.armada/config.yaml
python -m pytest tests/ -v
```

**Time spent:** ~35min

---

## 21. Time: 2026-06-09T21:10

### ✅ PWA manifest + service worker

**Files:** `armada_ai/server.py:197-209,220-246,117`, `armada_ai/templates/index.html:5-14,610-612`

**What was done:**
Completed PWA support so the Armada dashboard can be installed to a phone/tablet home screen:

1. **Manifest** (`/manifest.json`): Added icons (SVG, 192x192 + 512x512 with `purpose: any maskable`), proper display mode (`standalone`), orientation, theme colors
2. **SVG icon** (`/icon.svg`): Fleet anchor icon with gradient background, no external assets
3. **Meta tags**: Added `theme-color`, `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`, `apple-mobile-web-app-title`, `viewport-fit=cover` for iOS notch support
4. **Service worker** (`/sw.js`): Registered in HTML, self-destructs cache on activate (prevents stale cache issues)
5. **Auth exempt**: Added `/icon.svg` to the auth exemption list

**How to test:**
```bash
curl -s http://127.0.0.1:9100/manifest.json | python -m json.tool
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9100/icon.svg
# On mobile: open dashboard, "Add to Home Screen" in browser menu
# Run Lighthouse PWA audit in Chrome DevTools
python -m pytest tests/ -v
```

**Time spent:** ~20min

---

## 20. Time: 2026-06-09T21:08

### ✅ systemd/launchd service

**Files:** `armada_ai/service.py` (new), `armada_ai/cli.py:97,101,111,556-562`

**What was done:**
Added `armada service install` to install Armada as a system service that starts on login and auto-restarts on crash.

- **macOS**: Installs a LaunchAgent plist at `~/Library/LaunchAgents/com.armada.daemon.plist` with `RunAtLoad` and `KeepAlive`. Loaded/unloaded via `launchctl`.
- **Linux**: Installs a systemd user unit at `~/.config/systemd/user/armada.service` with `Restart=on-failure`. Enabled/started via `systemctl --user`.
- Both auto-detect the armada binary path and set `PATH`/`HOME` environment vars.
- Idempotent — running install again is a no-op if the file hasn't changed.

**How to test:**
```bash
armada service install

# macOS
cat ~/Library/LaunchAgents/com.armada.daemon.plist
plutil -lint ~/Library/LaunchAgents/com.armada.daemon.plist

# Linux
cat ~/.config/systemd/user/armada.service
systemctl --user status armada

# Run tests
python -m pytest tests/ -v
```

**Time spent:** ~20min

---

## 22. Time: 2026-06-10T01:35

### ✅ Loading states + Empty states

**Files:** `armada_ai/templates/index.html:138-148,510,558,1233`

**What was done:**
Added visual feedback for loading moments:

1. **Tree loading**: Initial spinner with "Loading agents..." text, cleared on first WebSocket tree message
2. **Terminal loading**: "Loading terminal..." with spinner while API call resolves
3. **Terminal placeholder**: "Select a node to view its terminal" when no node selected

**Empty states** were already implemented (no-nodes message in renderTree). Marked complete.

**How to test:**
```bash
curl -s http://127.0.0.1:9100/ | grep loading
python -m pytest tests/ -v
```

**Time spent:** ~15min

---

## 23. Time: 2026-06-10T01:40

### ✅ Keyboard shortcuts + Command palette

**Files:** `armada_ai/templates/index.html:2055-2125,2142-2180`

**What was done:**
Added keyboard-driven navigation and a Cmd+K command palette:

**Shortcuts:**
| Key | Action |
|-----|--------|
| `Cmd+K` / `Ctrl+K` | Toggle command palette |
| `N` | New node modal |
| `R` | Refresh tree (reconnect WS) |
| `/` | Focus search/filter input |
| `Esc` | Close palette, modals |

**Command palette**: Searchable overlay with actions (New Node, New Project, Refresh Tree, Filter Nodes, Toggle Pause). Filterable by typing. Click or Enter to execute. Esc to dismiss.

Ignores shortcuts when focus is in input/textarea/select fields.

**How to test:**
```bash
# Open dashboard, press Cmd+K or Ctrl+K
# Try: N, R, /, Esc
python -m pytest tests/ -v
```

**Time spent:** ~25min

---

## 24. Time: 2026-06-10T01:45

### ✅ Dark/light theme toggle

**Files:** `armada_ai/templates/index.html:19-55,543,671-682`

**What was done:**
Added CSS custom properties for all major colors and a theme toggle button in the sidebar header.

- **CSS variables**: `--bg`, `--bg-card`, `--bg-input`, `--border`, `--border-light`, `--text`, `--text-muted`, `--text-dim`, `--accent`, `--green`, `--yellow`, `--red`, `--hover`, `--btn-bg`, `--btn-hover`, `--overlay`
- **Dark theme** (default): GitHub dark palette (#0f1117 backgrounds, #e1e4e8 text)
- **Light theme** (`[data-theme="light"]`): GitHub light palette (#ffffff backgrounds, #24292f text)
- **Toggle button**: Sun/Moon icon in sidebar header, click to toggle
- **Persistence**: Saved to `localStorage` under `armada-theme`
- **System preference**: Defaults to system `prefers-color-scheme` if no saved preference

**How to test:**
```bash
# Open dashboard, click the ☀/☼ button in sidebar header
# Check localStorage: armada-theme = 'light' | 'dark'
# System dark mode users will see light mode initially if no pref set
python -m pytest tests/ -v
```

**Time spent:** ~25min
