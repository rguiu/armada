import os
import sys
import subprocess
import threading
import re
import json
import secrets
import socket
import asyncio
import time as _time
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from . import db
from . import naming
from . import tmux
from . import health
from . import logs
from . import metrics
from . import config
from . import constants

_ANSI_RE = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'
    r'|\x1b[()][0-9A-Z]'
    r'|\x1b[>=]'
)

app = FastAPI(title="Armada")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
TEMPLATE_DIR = Path(__file__).parent / "templates"
PID_FILE = constants.PID_FILE
TOKEN_FILE = constants.TOKEN_FILE
HOST = config.get("host")
PORT = config.get("port")

TOKEN = ""
SERVER_START_TS = 0.0

_ws_clients: set[WebSocket] = set()


async def _cleanup_ws_clients():
    dead = [ws for ws in _ws_clients if ws.client_state.name == "DISCONNECTED"]
    for ws in dead:
        _ws_clients.discard(ws)


async def _ws_cleanup_loop():
    while True:
        await asyncio.sleep(30)
        await _cleanup_ws_clients()


async def _broadcast_tree(hide_dead: bool = False):
    if not _ws_clients:
        return
    await _cleanup_ws_clients()
    tree = db.build_tree(include_dead=not hide_dead)
    payload = json.dumps({"type": "tree", "data": tree})
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            _ws_clients.discard(ws)


def _schedule_broadcast():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast_tree(), loop)
    except RuntimeError:
        pass


def _ensure_token(keep: bool = True):
    global TOKEN
    if not TOKEN:
        if keep and os.path.exists(TOKEN_FILE):
            TOKEN = Path(TOKEN_FILE).read_text().strip()
            if TOKEN:
                return TOKEN
        TOKEN = secrets.token_hex(16)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        Path(TOKEN_FILE).write_text(TOKEN)
    return TOKEN


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _check_token(request: Request) -> bool:
    token = request.query_params.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return token == TOKEN


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    exempt = ("/api/report", "/api/auth/status", "/favicon.ico", "/manifest.json", "/health", "/metrics", "/icon.svg")
    if path.startswith("/api/logs"):
        if not _check_token(request) and path not in exempt:
            logs.log_http_error(request.method, path, 401, "missing or invalid token")
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)
    if path.startswith("/api/") and path not in exempt and not path.endswith("/ws"):
        if not _check_token(request):
            logs.log_http_error(request.method, path, 401, "missing or invalid token")
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self' ws: wss:; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.middleware("http")
async def csp_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP_HEADER
    return response


@app.on_event("startup")
async def startup():
    global SERVER_START_TS
    SERVER_START_TS = _time.time()
    metrics.init()
    db.init_db()
    try:
        tmux.ensure_armada_session()
    except RuntimeError:
        pass
    logs.log_server_start()
    recovered = health.recover_on_startup()
    if recovered:
        names = [n["name"] for n in recovered]
        logs.log_event("_server", "recovery", {"recovered_nodes": names})
        # Broadcast recovery notification to WebSocket clients once connected
        def _notify_recovery():
            _time.sleep(2)
            try:
                for name in names:
                    db.add_status_report(
                        next((n["id"] for n in recovered if n["name"] == name), 0),
                        "idle", "server restarted — reconnected to agent")
            except Exception:
                pass
        threading.Thread(target=_notify_recovery, daemon=True).start()
    health.start_health_loop(interval=config.get("health_interval"))
    asyncio.create_task(_ws_cleanup_loop())
    logs.log_event("_server", "ready", {"port": PORT, "recovered": len(recovered)})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logs.log_http_error(request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logs.log_http_error(request.method, request.url.path, 500, str(exc))
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


# --- Static files ---

@app.get("/manifest.json")
def manifest():
    return JSONResponse({
        "name": "Armada Fleet Dashboard",
        "short_name": "Armada",
        "description": "Command your fleet of AI agents",
        "start_url": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0f1117",
        "theme_color": "#0f1117",
        "icons": [
            {"src": "/icon.svg", "sizes": "192x192", "type": "image/svg+xml", "purpose": "any"},
            {"src": "/icon.svg", "sizes": "512x512", "type": "image/svg+xml", "purpose": "any maskable"},
        ]
    })


@app.get("/sw.js")
def service_worker():
    sw = """\
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => {
  caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k))));
  e.waitUntil(clients.claim());
});"""
    return Response(content=sw, media_type="application/javascript")


@app.get("/icon.svg")
def app_icon():
    icon = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="92" fill="url(#bg)"/>
  <g transform="translate(256,256)" fill="none" stroke="#58a6ff" stroke-width="28" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="-40" cy="-60" r="32"/>
    <circle cx="40" cy="-60" r="32"/>
    <circle cx="0" cy="20" r="32"/>
    <line x1="-40" y1="-28" x2="0" y2="-12"/>
    <line x1="40" y1="-28" x2="0" y2="-12"/>
    <line x1="0" y1="52" x2="0" y2="160"/>
    <line x1="-80" y1="160" x2="80" y2="160"/>
    <path d="M-160,200 Q0,260 160,200" stroke-width="22"/>
  </g>
</svg>"""
    return Response(content=icon, media_type="image/svg+xml")


# --- Dashboard ---

@app.get("/", response_class=HTMLResponse)
def dashboard_page():
    html_path = TEMPLATE_DIR / "index.html"
    if html_path.exists():
        html = html_path.read_text()
        meta = f'<meta name="armada-token" content="{TOKEN}">'
        html = html.replace("<head>", "<head>\n" + meta, 1)
        return html
    return HTMLResponse("<h1>Dashboard not found</h1>")


# --- Tree & Nodes ---

@app.get("/api/tree")
def get_tree(hide_dead: bool = False):
    return JSONResponse(db.build_tree(include_dead=not hide_dead))


@app.websocket("/api/ws")
async def tree_ws(websocket: WebSocket):
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
    token = websocket.query_params.get("token")
    if not token:
        auth = websocket.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token != TOKEN:
        logs.log_ws_disconnect(client, "/api/ws", "bad_token")
        await websocket.close(code=4001)
        return

    await websocket.accept()
    _ws_clients.add(websocket)
    logs.log_ws_connect(client, "/api/ws")
    try:
        tree = db.build_tree(include_dead=True)
        await websocket.send_text(json.dumps({"type": "tree", "data": tree}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logs.log_event("_server", "ws_error", {"client": client, "path": "/api/ws", "error": str(e)})
    finally:
        _ws_clients.discard(websocket)
        logs.log_ws_disconnect(client, "/api/ws")


@app.get("/api/nodes")
def list_nodes(hide_dead: bool = False):
    return JSONResponse(db.get_all_nodes(include_dead=not hide_dead))


@app.get("/api/nodes/history")
def list_killed_nodes(limit: int = 50):
    return JSONResponse(db.get_killed_nodes(limit))


@app.get("/api/nodes/{node_id}")
def get_node(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    reports = db.get_node_reports(node_id)
    children = db.get_node_children(node_id)
    return JSONResponse({"node": node, "reports": reports, "children": children})


@app.get("/api/nodes/{node_id}/reports")
def get_reports(node_id: int, limit: int = 30):
    return JSONResponse(db.get_node_reports(node_id, limit))


@app.post("/api/nodes")
async def create_node(request: Request):
    body = await request.json()
    name = body.get("name") or None
    parent_id = body.get("parent_id") or None
    project_label_id = body.get("project_label_id") or None
    agent_type = body.get("agent_type", "auto")
    initial_prompt = (body.get("initial_prompt") or "").strip()

    if not project_label_id:
        raise HTTPException(status_code=400, detail="A project must be selected")

    if name and len(name) > 100:
        raise HTTPException(status_code=400, detail="Node name must be 100 characters or fewer")

    existing_names = db.existing_names()

    if name and name in existing_names:
        raise HTTPException(status_code=409, detail=f"Node '{name}' already exists")

    path = db.get_project_label_path(project_label_id)
    if not path:
        raise HTTPException(status_code=400, detail="Project label not found")
    if not os.path.isdir(path):
        raise HTTPException(status_code=400,
            detail=f"Project path does not exist: {path}")
    working_dir = path

    if parent_id:
        parent = db.get_node(parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent node not found")

    colour = naming.next_colour(db.active_colours())

    if name:
        agent_name = name
    else:
        agent_name = naming.generate_sequential_name(project_label_id, existing_names)

    pane_id = tmux.create_node_window(
        name=agent_name, colour=colour, working_dir=working_dir,
        agent_type=agent_type,
    )

    if pane_id is None:
        raise HTTPException(status_code=500,
            detail="Failed to create tmux window. Is tmux installed and running?")

    node_id = db.create_node(
        name=agent_name,
        colour=colour,
        parent_id=parent_id,
        project_label_id=project_label_id,
        tmux_pane_id=pane_id,
        agent_type=agent_type,
    )

    db.add_status_report(node_id, "idle",
        f"node created (agent={agent_type}, project={project_label_id or 'cwd'})")
    logs.log_create(agent_name, agent_type, project_label_id)
    metrics.counter_inc("armada_nodes_created_total")
    tmux.save_agent_hook(agent_name)

    if initial_prompt:
        delay = 8.0 if agent_type in ("opencode", "claude") else 3.0
        tmux.send_initial_prompt(agent_name, initial_prompt, delay=delay)

    node = db.get_node(node_id)
    await _broadcast_tree()
    return JSONResponse(node, status_code=201)


@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    killed = db.kill_node(node_id)
    for entry in killed:
        try:
            content = tmux.capture_pane_content(entry["name"])
            if content:
                logs.log_agent_output(entry["name"], content)
        except Exception:
            pass
        try:
            tmux.kill_node_window(entry["name"])
        except Exception:
            pass
        logs.log_kill(entry["name"])

    _schedule_broadcast()
    return JSONResponse({"ok": True, "killed": len(killed)})


@app.post("/api/nodes/{node_id}/send")
async def send_to_node(node_id: int, request: Request):
    body = await request.json()
    command = body.get("command", "").strip()
    raw = body.get("raw", False)
    if not command:
        raise HTTPException(status_code=400, detail="command is required")

    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if node.get("status") == "dead":
        raise HTTPException(status_code=410, detail="Node is dead")

    if not tmux.window_exists(node["name"]):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    ok = tmux.send_raw_keys(node["name"], command) if raw else tmux.send_keys(node["name"], command)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send command")

    logs.log_send(node["name"], command)
    return JSONResponse({"ok": True})


@app.patch("/api/nodes/{node_id}")
async def patch_node(node_id: int, request: Request):
    body = await request.json()
    action = body.get("action")
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    if action == "hide":
        hidden = db.hide_node(node_id)
        await _broadcast_tree()
        return JSONResponse({"ok": True, "hidden": len(hidden)})
    if action == "reparent":
        new_parent = body.get("parent_id") or None
        if new_parent:
            parent_node = db.get_node(new_parent)
            if not parent_node:
                raise HTTPException(status_code=400, detail="Parent node not found")
        db.reparent_node(node_id, new_parent)
        await _broadcast_tree()
        return JSONResponse({"ok": True})
    if action == "rename":
        new_name = body.get("name", "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="name is required")
        existing = db.existing_names()
        if new_name in existing:
            raise HTTPException(status_code=409, detail=f"Node '{new_name}' already exists")
        db.rename_node(node_id, new_name)
        await _broadcast_tree()
        return JSONResponse({"ok": True})
    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@app.post("/api/nodes/{node_id}/attach")
def attach(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not tmux.window_exists(node["name"]):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    error = tmux.attach_node(node["name"], node["colour"])
    if error:
        raise HTTPException(status_code=500, detail=error)

    logs.log_attach(node["name"])
    return JSONResponse({"ok": True})


@app.get("/api/nodes/{node_id}/terminal")
def terminal_view(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not tmux.window_exists(node["name"]):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    target = f"armada-{node['name']}"

    dims = subprocess.run(
        ["tmux", "display-message", "-p", "-t", target,
         "#{pane_width} #{pane_height}"],
        capture_output=True, timeout=2,
    )
    cols, rows = 80, 24
    if dims.returncode == 0:
        parts = dims.stdout.decode().strip().split()
        if len(parts) == 2:
            cols, rows = int(parts[0]), int(parts[1])

    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", target],
        capture_output=True, timeout=2,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail="Failed to capture pane")

    raw = _ANSI_RE.sub('', result.stdout.decode("utf-8", errors="replace")).replace('\r', '')
    text_lines = raw.split('\n')
    if text_lines and text_lines[-1] == '':
        text_lines.pop()
    text = '\r\n'.join(text_lines)
    return JSONResponse({"text": text, "cols": cols, "rows": rows})


@app.websocket("/api/nodes/{node_id}/ws")
async def terminal_ws(websocket: WebSocket, node_id: int):
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
    token = websocket.query_params.get("token")
    if not token:
        auth = websocket.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token != TOKEN:
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws", "bad_token")
        await websocket.close(code=4001)
        return

    node = db.get_node(node_id)
    if not node:
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws", "node_not_found")
        await websocket.close(code=4004)
        return
    if not tmux.window_exists(node["name"]):
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws", "window_gone")
        await websocket.close(code=4004)
        return

    target = f"armada-{node['name']}"
    await websocket.accept()
    logs.log_ws_connect(client, f"/api/nodes/{node_id}/ws")

    poll_interval = 0.8
    last_text = ""

    async def poll_pane():
        nonlocal last_text
        pane_cols = 80
        pane_rows = 24
        while True:
            await asyncio.sleep(poll_interval)
            try:
                dims = await asyncio.to_thread(
                    lambda: subprocess.run(
                        ["tmux", "display-message", "-p", "-t", target,
                         "#{pane_width} #{pane_height}"],
                        capture_output=True, timeout=2,
                    )
                )
                if dims.returncode == 0:
                    parts = dims.stdout.decode().strip().split()
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        pane_cols = int(parts[0])
                        pane_rows = int(parts[1])

                result = await asyncio.to_thread(
                    lambda: subprocess.run(
                        ["tmux", "capture-pane", "-e", "-p", "-t", target],
                        capture_output=True, timeout=2,
                    )
                )
                if result.returncode != 0:
                    continue

                raw = result.stdout.decode("utf-8", errors="replace").replace('\r', '')
                text_lines = raw.split('\n')
                while text_lines and text_lines[-1] == '':
                    text_lines.pop()
                if text_lines:
                    text_lines.pop()
                text = '\r\n'.join(text_lines)

                if text != last_text:
                    last_text = text
                    await websocket.send_text(json.dumps({
                        "cols": pane_cols,
                        "rows": pane_rows,
                        "text": text,
                    }))
            except WebSocketDisconnect:
                break
            except Exception as e:
                logs.log_event("_server", "ws_poll_error", {"client": client, "node_id": node_id, "error": str(e)})

    async def recv_keys():
        while True:
            try:
                data = await websocket.receive_text()
                if data:
                    await asyncio.to_thread(
                        lambda: tmux.send_raw_keys(node["name"], data)
                    )
            except WebSocketDisconnect:
                break
            except Exception as e:
                logs.log_event("_server", "ws_recv_error", {"client": client, "node_id": node_id, "error": str(e)})

    try:
        await asyncio.gather(poll_pane(), recv_keys())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logs.log_event("_server", "ws_term_error", {"client": client, "node_id": node_id, "error": str(e)})
    finally:
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws")


# --- Project Labels ---

@app.get("/api/project-labels")
def list_project_labels():
    return JSONResponse(db.list_project_labels())


@app.post("/api/project-labels")
async def create_project_label(request: Request):
    body = await request.json()
    id = body.get("id", "").strip()
    name = body.get("name", "").strip()
    path = body.get("path", "").strip()

    if not id or not name:
        raise HTTPException(status_code=400, detail="id and name are required")
    if not path:
        path = os.getcwd()

    try:
        db.add_project_label(id, name, os.path.abspath(path))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return JSONResponse({"ok": True}, status_code=201)


@app.delete("/api/project-labels/{label_id}")
def delete_project_label(label_id: str):
    db.delete_project_label(label_id)
    return JSONResponse({"ok": True})


@app.get("/api/project-labels/{label_id}/overview")
def project_overview(label_id: str):
    labels = db.list_project_labels()
    label = next((lb for lb in labels if lb["id"] == label_id), None)
    if not label:
        raise HTTPException(status_code=404, detail="Project not found")

    path = label["path"]
    is_dir = os.path.isdir(path)
    skills = tmux.list_project_skills(path)["skills"] if is_dir else []
    nodes = db.get_nodes_by_project_label_id(label_id)
    plugins = tmux.list_project_plugins(path)["plugins"] if is_dir else []
    hooks = tmux.list_project_hooks(path)["hooks"] if is_dir else []
    configs = tmux.get_project_config(path)["configs"] if is_dir else {}
    git = tmux.get_project_git_info(path)["git"] if is_dir else {}

    return JSONResponse({
        "label": label,
        "skills": skills,
        "nodes": nodes,
        "plugins": plugins,
        "hooks": hooks,
        "configs": configs,
        "git": git,
    })


@app.get("/api/skills")
def global_skills():
    return JSONResponse(tmux.list_project_skills(os.path.expanduser("~")))


# --- Maintenance ---

@app.post("/api/refresh-hooks")
def refresh_hooks():
    labels = db.list_project_labels()
    updated = []
    for label in labels:
        path = label["path"]
        if not os.path.isdir(path):
            continue
        try:
            tmux.install_skills(path)
            tmux.deploy_claude_hooks(path)
            updated.append(label["id"])
        except Exception:
            pass
    return JSONResponse({"updated": updated})


# --- Agent Report ---

@app.post("/api/report")
async def agent_report(request: Request):
    body = await request.json()
    name = body.get("name")
    status = body.get("status", "idle")
    message = body.get("message")
    tokens = body.get("tokens")
    cost = body.get("cost")

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if status not in ("active", "idle", "error", "pending"):
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    node = db.get_node_by_name(name)
    if not node:
        raise HTTPException(status_code=404, detail=f"Unknown node: {name}")

    db.add_status_report(node["id"], status, message)
    logs.log_report(name, status, message)
    metrics.counter_inc("armada_reports_total")
    report_latency = _time.time() - (body.get("_client_ts") or 0)
    if report_latency > 0 and report_latency < 3600:
        metrics.histogram_observe("armada_report_latency_seconds", report_latency)
    if status == "error":
        metrics.counter_inc("armada_errors_total")
    if tokens or cost:
        db.accumulate_cost(
            node["id"],
            tokens_in=tokens.get("input", 0) if tokens else 0,
            tokens_out=tokens.get("output", 0) if tokens else 0,
            cost=cost or 0.0,
        )
        if tokens:
            metrics.counter_inc("armada_tokens_total", tokens.get("input", 0), ("input",))
            metrics.counter_inc("armada_tokens_total", tokens.get("output", 0), ("output",))
    await _broadcast_tree()
    return JSONResponse({"ok": True})


# --- Logs ---

_SAFE_LOG_NAME = re.compile(r'^[a-zA-Z0-9_][-a-zA-Z0-9_]*$')


@app.get("/api/logs/{node_name}")
def get_node_logs(node_name: str, limit: int = 50, before: float | None = None):
    if not _SAFE_LOG_NAME.match(node_name):
        raise HTTPException(status_code=400, detail="Invalid node name")
    if not db.get_node_by_name(node_name) and node_name not in db.existing_names() and node_name != "_server":
        raise HTTPException(status_code=404, detail="Node not found")
    entries = logs.get_node_logs(node_name, limit=limit, before_ts=before)
    return JSONResponse({"node": node_name, "count": len(entries), "entries": entries})


@app.get("/api/logs")
def search_all_logs(q: str = "", limit: int = 50, node: str | None = None):
    if not q:
        return JSONResponse({"query": q, "count": 0, "entries": []})
    entries = logs.search_logs(q, limit=limit, node_name=node)
    return JSONResponse({"query": q, "count": len(entries), "entries": entries})


@app.get("/api/server-log")
def get_server_log(limit: int = 100):
    entries = logs.get_node_logs("_server", limit=limit)
    return JSONResponse({"count": len(entries), "entries": entries, "path": os.path.expanduser("~/.armada/logs/_server.jsonl")})


@app.post("/api/client-log")
async def client_log(request: Request):
    body = await request.json()
    level = body.get("level", "info")
    message = body.get("message", "")[:500]
    logs.log_event("_client", level, {"message": message})
    return JSONResponse({"ok": True})


# --- Auth & Info ---

@app.get("/api/info")
def server_info():
    uptime_seconds = _time.time() - SERVER_START_TS if SERVER_START_TS else 0
    return JSONResponse({
        "lan_ip": _lan_ip(),
        "port": PORT,
        "uptime": round(uptime_seconds, 1),
        "version": constants.VERSION,
        "started_at": SERVER_START_TS,
    })


@app.get("/health")
def health_check():
    uptime_seconds = _time.time() - SERVER_START_TS if SERVER_START_TS else 0
    metrics.gauge_set("armada_uptime_seconds", uptime_seconds)
    nodes = db.get_all_nodes(include_dead=False)
    active = sum(1 for n in nodes if n["status"] == "active")
    pending = sum(1 for n in nodes if n["status"] == "pending")
    idle = sum(1 for n in nodes if n["status"] == "idle")
    metrics.gauge_set("armada_agents", active, ("active",))
    metrics.gauge_set("armada_agents", pending, ("pending",))
    metrics.gauge_set("armada_agents", idle, ("idle",))
    return JSONResponse({
        "status": "ok",
        "agents": len(nodes),
        "active": active,
        "pending": pending,
        "idle": idle,
        "uptime": round(uptime_seconds, 1),
        "version": constants.VERSION,
    })


@app.get("/metrics")
def prometheus_metrics():
    uptime_seconds = _time.time() - SERVER_START_TS if SERVER_START_TS else 0
    metrics.gauge_set("armada_uptime_seconds", uptime_seconds)
    nodes = db.get_all_nodes(include_dead=False)
    statuses = {"active": 0, "pending": 0, "idle": 0}
    for n in nodes:
        s = n["status"]
        if s in statuses:
            statuses[s] += 1
    for s, count in statuses.items():
        metrics.gauge_set("armada_agents", count, (s,))
    total_cost = sum(n.get("total_cost", 0) or 0 for n in nodes)
    metrics.gauge_set("armada_cost_total", total_cost)
    return Response(content=metrics.generate_latest(), media_type="text/plain; charset=utf-8")


@app.get("/api/qr")
def qr_code(url: str = ""):
    import io
    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@app.get("/api/auth/status")
def auth_status(request: Request):
    token = request.query_params.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return JSONResponse({
        "valid": token == TOKEN,
        "has_token": bool(TOKEN),
        "server_alive": True,
        "uptime": round(_time.time() - SERVER_START_TS, 1) if SERVER_START_TS else 0,
    })


# --- Daemon ---

def _write_pid():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def _remove_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _daemonize():
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    os.chdir("/")
    os.umask(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)
    _write_pid()


def start_server(daemon: bool = True, open_browser: bool = True, lan: bool = False, keep_token: bool = True):
    host = "0.0.0.0" if lan else HOST
    _ensure_token(keep=keep_token)

    if daemon:
        _daemonize()
    else:
        _write_pid()

    if open_browser and not lan:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{PORT}")).start()

    try:
        uvicorn.run(app, host=host, port=PORT, log_level="warning")
    finally:
        logs.log_server_stop()
        _remove_pid()
