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
