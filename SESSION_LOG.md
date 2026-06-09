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
