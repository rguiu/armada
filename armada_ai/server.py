"""FastAPI server — refactored to delegate business logic to domain/infrastructure layers.

Maintains backward-compatible module-level exports (TOKEN, app, start_server, etc.)
so existing tests and CLI continue to work unchanged.
"""
import os
import sys
import shutil
import subprocess
import threading
import re
import json
import asyncio
import time as _time
from datetime import datetime as _datetime
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from . import constants
from . import config
from . import logs
from . import metrics
from . import naming
from .infrastructure import database as db
from . import tmux as tmux
from .infrastructure.auth_manager import TokenManager, AuthExemptPaths
from .infrastructure import deployment
from .project_explorer import (
    list_project_skills, list_project_plugins, list_project_hooks,
    get_project_config, get_project_git_info,
)
from .domain.models import AgentStatus, CreateNodeRequest, AgentReportRequest, Node
from .transport.middleware import _CSP_HEADER
from .transport.static_assets import manifest_route, service_worker_route, app_icon_route


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

HOST = config.get("host")
PORT = config.get("port")

_token_manager = TokenManager(constants.TOKEN_FILE)
TOKEN = ""  # backward compat: set during startup
SERVER_START_TS = 0.0

_ws_clients: set[WebSocket] = set()
_restart_lock = threading.Lock()
_restarting_nodes: set[str] = set()
_create_lock: asyncio.Lock | None = None


# --- WebSocket broadcast ---

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


# --- Auth (delegated to auth_manager) ---

def _ensure_token(keep: bool = True):
    global TOKEN
    TOKEN = _token_manager.ensure(keep=keep)
    return TOKEN


def _lan_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _check_token(request: Request) -> bool:
    token = TokenManager.extract_from_request(request)
    return bool(token and token == TOKEN)


# --- Middleware ---


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if path.startswith("/api/logs"):
        if (not _check_token(request) and path not in AuthExemptPaths.EXEMPT
                and not path.endswith("/ws")):
            logs.log_http_error(request.method, path, 401, "missing or invalid token")
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    if (path.startswith("/api/") and path not in AuthExemptPaths.EXEMPT
            and not path.endswith("/ws")):
        if not _check_token(request):
            logs.log_http_error(request.method, path, 401, "missing or invalid token")
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    return await call_next(request)


@app.middleware("http")
async def csp_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP_HEADER
    return response


# --- Startup ---

@app.on_event("startup")
async def startup():
    global SERVER_START_TS, TOKEN
    SERVER_START_TS = _time.time()
    TOKEN = _token_manager.ensure(keep=True)
    metrics.init()
    db.init_db()
    try:
        tmux.ensure_armada_session()
    except RuntimeError:
        pass
    logs.log_server_start()

    recovered = _recover_on_startup()
    if recovered:
        names = [n["name"] for n in recovered]
        logs.log_event("_server", "recovery", {"recovered_nodes": names})
        def _notify_recovery():
            _time.sleep(2)
            try:
                for n in recovered:
                    node = db.get_node(n["id"])
                    status = node.status if node else "idle"
                    db.add_status_report(n["id"], status,
                                         "server restarted — reconnected to agent")
            except Exception:
                pass
        threading.Thread(target=_notify_recovery, daemon=True).start()

    _start_health_loop(interval=config.get("health_interval"))
    asyncio.create_task(_ws_cleanup_loop())
    logs.log_event("_server", "ready", {"port": PORT, "recovered": len(recovered)})


def _recover_on_startup():
    running = tmux.running_window_names()
    if not running:
        return []
    live = db.recover_live_nodes(running)
    recovered = []
    for node in live:
        name = node.name
        if name not in running:
            continue
        logs.log_recover(name)
        db.add_status_report(node.id, node.status,
            "server restarted — reconnected to tmux window")
        if not node.tmux_session_id:
            sid = tmux.get_session_id(name)
            if sid:
                db.update_node_status(node.id, node.status,
                                      tmux_session_id=sid)
        recovered.append(node.as_summary())
    db.recover_nodes(running)
    return recovered


def _start_health_loop(interval: int = 15):
    _tick = 0

    def check():
        nonlocal _tick
        while True:
            _time.sleep(interval)
            _tick += 1
            try:
                _run_health_check()
            except Exception:
                pass
            if _tick % 20 == 0:
                try:
                    db.prune_all_old_reports()
                    db.vacuum_db()
                    logs.rotate_logs()
                    logs.cleanup_old_rotated_logs()
                except Exception:
                    pass
            if _tick % 4 == 0:
                try:
                    db.snapshot_stats()
                except Exception:
                    pass

    threading.Thread(target=check, daemon=True).start()


def _run_health_check():
    nodes = db.get_all_nodes(include_dead=False)
    if not nodes:
        return
    now = _time.time()

    for node in nodes:
        if node.tmux_pane_id and tmux.pane_alive(node.tmux_pane_id):
            continue
        if not node.tmux_pane_id and tmux.window_exists(node.name):
            continue
        if node.created_at:
            try:
                created = _datetime.fromisoformat(node.created_at).timestamp()
                if now - created < 15:
                    continue
            except (ValueError, TypeError):
                pass
        logs.log_health(node.name, dead=True)
        _mark_node_dead(node.id)
        _auto_restart_node(node)

    _resurrect_dead_nodes()


def _resurrect_dead_nodes():
    dead_nodes = [n for n in db.get_all_nodes(include_dead=True)
                  if n.is_dead() and n.tmux_pane_id]
    for node in dead_nodes:
        if tmux.pane_alive(node.tmux_pane_id):
            db.update_node_status(node.id, "idle")
            logs.log_recover(node.name)


def _mark_node_dead(node_id: int):
    dead = db.kill_node(node_id)
    for entry in dead:
        name = entry["name"]
        try:
            content = tmux.capture_pane_content(name)
            if content:
                logs.log_agent_output(name, content)
        except Exception:
            pass
        try:
            tmux.kill_node_window(name)
        except Exception:
            pass


def _auto_restart_node(node):
    name = node.name
    with _restart_lock:
        if name in _restarting_nodes:
            return
        _restarting_nodes.add(name)
    try:
        restart_count = db.get_restart_count_for_name(name)
        if restart_count >= constants.MAX_RESTARTS:
            logs.log_event(name, "restart_limit", {"count": restart_count}, level="error")
            return
        working_dir = db.get_project_label_path(node.project_label_id) or os.getcwd()
        result = tmux.create_node_window(
            name=name, colour=node.colour,
            working_dir=working_dir, agent_type=node.agent_type,
        )
        pane_id, session_id = result.pane_id, result.session_id
        if pane_id:
            nid = db.create_node(
                name=name, colour=node.colour, parent_id=None,
                project_label_id=node.project_label_id,
                tmux_pane_id=pane_id, tmux_session_id=session_id,
                agent_type=node.agent_type,
            )
            db.add_status_report(nid, "active",
                f"auto-restarted (attempt {restart_count + 1}/{constants.MAX_RESTARTS})")
            db.increment_restart_count(name)
            logs.log_event(name, "restarted", {
                "attempt": restart_count + 1,
                "agent_type": node.agent_type,
            }, level="warn")
    except Exception as e:
        logs.log_event(name, "restart_failed", {"error": str(e)}, level="error")
    finally:
        with _restart_lock:
            _restarting_nodes.discard(name)


# --- Exception handlers ---

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
    return manifest_route()


@app.get("/sw.js")
def service_worker():
    return service_worker_route()


@app.get("/icon.svg")
def app_icon():
    return app_icon_route()


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
    token = TokenManager.extract_from_websocket(websocket)
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
    nodes = db.get_all_nodes(include_dead=not hide_dead)
    return JSONResponse([n.as_summary() for n in nodes])


@app.get("/api/nodes/history")
def list_killed_nodes(limit: int = 50):
    nodes = db.get_killed_nodes(limit)
    return JSONResponse([n.as_summary() for n in nodes])


@app.get("/api/nodes/{node_id}")
def get_node(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    reports = db.get_node_reports(node_id)
    children = db.get_node_children(node_id)
    return JSONResponse({
        "node": node.as_summary(),
        "reports": reports,
        "children": [c.as_summary() for c in children],
    })


@app.get("/api/nodes/{node_id}/reports")
def get_reports(node_id: int, limit: int = 30):
    return JSONResponse(db.get_node_reports(node_id, limit))


@app.get("/api/nodes/{node_id}/children-output")
def get_children_output(node_id: int):
    """Capture pane content from all live children of a node."""
    children = db.get_node_children(node_id)
    outputs = []
    for child in children:
        if tmux.window_exists(child.name):
            content = tmux.capture_pane_content(child.name, max_lines=50)
            outputs.append({
                "id": child.id,
                "name": child.name,
                "colour": child.colour,
                "status": child.status,
                "content": content.strip() if content else "",
            })
    return JSONResponse(outputs)


@app.post("/api/nodes")
async def create_node(request: Request):
    body = await request.json()
    req = CreateNodeRequest(
        name=body.get("name") or None,
        project_label_id=body.get("project_label_id") or None,
        agent_type=body.get("agent_type", "auto"),
        parent_id=body.get("parent_id") or None,
        initial_prompt=(body.get("initial_prompt") or "").strip() or None,
    )

    if not req.project_label_id:
        raise HTTPException(status_code=400, detail="A project must be selected")

    global _create_lock
    if _create_lock is None:
        _create_lock = asyncio.Lock()
    async with _create_lock:
        existing_names = db.existing_names()
        validation_error = req.validate_name(existing_names)
        if isinstance(validation_error, str):
            if "already exists" in validation_error:
                raise HTTPException(status_code=409, detail=validation_error)
            raise HTTPException(status_code=400, detail=validation_error)

        colour = naming.next_colour(db.active_colours())
        agent_name = req.name or naming.generate_sequential_name(
            req.project_label_id, existing_names)
        agent_name = agent_name.replace(".", "-")

    path = db.get_project_label_path(req.project_label_id)
    if not path:
        raise HTTPException(status_code=400, detail="Project label not found")
    if not os.path.isdir(path):
        raise HTTPException(status_code=400,
            detail=f"Project path does not exist: {path}")

    if req.parent_id:
        parent = db.get_node(req.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent node not found")

    # Deploy skills/hooks before creating tmux window
    await asyncio.to_thread(deployment.deploy_for_agent_type, agent_name, req.agent_type, path)

    result = await asyncio.to_thread(
        tmux.create_node_window,
        name=agent_name, colour=colour, working_dir=path,
        agent_type=req.agent_type,
    )
    if not result or not result.ok:
        error_detail = result.error if result else "create_node_window returned None"
        raise HTTPException(status_code=500,
            detail=f"Failed to create tmux session: {error_detail}")
    pane_id, session_id = result.pane_id, result.session_id

    try:
        node_id = db.create_node(
            name=agent_name, colour=colour, parent_id=req.parent_id,
            project_label_id=req.project_label_id, tmux_pane_id=pane_id,
            tmux_session_id=session_id,
            agent_type=req.agent_type,
        )
    except Exception:
        try:
            tmux.kill_node_window(agent_name)
        except Exception:
            pass
        raise

    db.add_status_report(node_id, "idle",
        f"node created (agent={req.agent_type}, project={req.project_label_id or 'cwd'})")
    logs.log_create(agent_name, req.agent_type, req.project_label_id)
    metrics.counter_inc("armada_nodes_created_total")

    if req.initial_prompt:
        delay = 8.0 if req.agent_type in ("opencode", "claude", "aap_opencode", "aap_claude") else 3.0
        tmux.send_initial_prompt(agent_name, req.initial_prompt, delay=delay)

    node = db.get_node(node_id)
    await _broadcast_tree()
    return JSONResponse(node.as_summary(), status_code=201)


@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    import sqlite3 as _sqlite3
    killed = []
    try:
        for _attempt in range(10):
            try:
                killed = db.kill_node(node_id)
                break
            except _sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and _attempt < 9:
                    _time.sleep(0.1 * (_attempt + 1))
                    continue
                raise
    except Exception:
        # DB exhausted retries — still kill the tmux session
        try:
            tmux.kill_node_window(node.name)
        except Exception:
            pass
        raise
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
        db.add_status_report(entry["id"], "dead", "killed by user")

    _schedule_broadcast()
    return JSONResponse({"ok": True, "killed": len(killed)})


@app.post("/api/nodes/{node_id}/send")
async def send_to_node(node_id: int, request: Request):
    body = await request.json()
    raw = body.get("raw", False)
    command = body.get("command", "") if raw else body.get("command", "").strip()
    if not command and not raw:
        raise HTTPException(status_code=400, detail="command is required")

    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if node.is_dead():
        raise HTTPException(status_code=410, detail="Node is dead")
    if not tmux.window_exists(node.name):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    if raw:
        ok = await asyncio.to_thread(tmux.send_raw_keys, node.name, command)
    else:
        ok = await asyncio.to_thread(tmux.send_keys, node.name, command)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send command")

    logs.log_send(node.name, command)
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
        for entry in hidden:
            try:
                tmux.kill_node_window(entry["name"])
            except Exception:
                pass
            logs.log_kill(entry["name"])
            db.add_status_report(entry["id"], "dead", "deleted by user")
        await _broadcast_tree()
        return JSONResponse({"ok": True, "hidden": len(hidden)})
    if action == "reparent":
        new_parent = body.get("parent_id") or None
        if new_parent:
            if not db.get_node(new_parent):
                raise HTTPException(status_code=400, detail="Parent node not found")
        db.reparent_node(node_id, new_parent)
        await _broadcast_tree()
        return JSONResponse({"ok": True})
    if action == "rename":
        new_name = body.get("name", "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="name is required")
        if new_name in db.existing_names():
            raise HTTPException(status_code=409, detail=f"Node '{new_name}' already exists")
        old_name = db.get_node(node_id).name if db.get_node(node_id) else None
        db.rename_node(node_id, new_name)
        if old_name:
            tmux.rename_node_session(old_name, new_name)
        await _broadcast_tree()
        return JSONResponse({"ok": True})
    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@app.post("/api/nodes/{node_id}/attach")
def attach(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not tmux.window_exists(node.name):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    error = tmux.attach_node(node.name, node.colour, node.tmux_session_id)
    if error:
        raise HTTPException(status_code=500, detail=error)

    logs.log_attach(node.name)
    return JSONResponse({"ok": True})


@app.get("/api/nodes/{node_id}/terminal")
def terminal_view(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not tmux.window_exists(node.name):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    target = f"armada-{node.name}"

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
    token = TokenManager.extract_from_websocket(websocket)
    if token != TOKEN:
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws", "bad_token")
        await websocket.close(code=4001)
        return

    node = db.get_node(node_id)
    if not node:
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws", "node_not_found")
        await websocket.close(code=4004)
        return
    if not tmux.window_exists(node.name):
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws", "window_gone")
        await websocket.close(code=4004)
        return

    target = f"armada-{node.name}"
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
                        "cols": pane_cols, "rows": pane_rows, "text": text,
                    }))
            except WebSocketDisconnect:
                break
            except Exception as e:
                logs.log_event("_server", "ws_poll_error",
                               {"client": client, "node_id": node_id, "error": str(e)})

    async def recv_keys():
        while True:
            try:
                data = await websocket.receive_text()
                if data:
                    await asyncio.to_thread(
                        lambda: tmux.send_raw_keys(node.name, data)
                    )
            except WebSocketDisconnect:
                break
            except Exception as e:
                logs.log_event("_server", "ws_recv_error",
                               {"client": client, "node_id": node_id, "error": str(e)})

    try:
        await asyncio.gather(poll_pane(), recv_keys())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logs.log_event("_server", "ws_term_error",
                       {"client": client, "node_id": node_id, "error": str(e)})
    finally:
        logs.log_ws_disconnect(client, f"/api/nodes/{node_id}/ws")


# --- Task Mailbox ---

def _deliver_pending_messages(node: Node) -> int:
    if not node.is_alive() or not tmux.window_exists(node.name):
        return 0
    messages = db.get_pending_messages_for_node(node.id)
    if not messages:
        return 0
    delivered = 0
    for msg in messages:
        sender = msg.from_node_name or f"node-{msg.from_node_id}" if msg.from_node_id else "system"
        try:
            payload_preview = json.loads(msg.payload) if msg.payload.startswith("{") else msg.payload
        except (json.JSONDecodeError, AttributeError):
            payload_preview = msg.payload
        if isinstance(payload_preview, dict):
            text = payload_preview.get("body", payload_preview.get("command", json.dumps(payload_preview)))
        else:
            text = str(payload_preview)
        if node.agent_type in ("bash", "auto"):
            tmux.send_keys(node.name, "armada-node-check-inbox")
            db.mark_message_delivered(msg.id)
            delivered += 1
            break
        else:
            content = f"[armada-message from={sender} type={msg.type} id={msg.id}]\n{text}"
            if tmux.send_keys(node.name, content):
                db.mark_message_delivered(msg.id)
                delivered += 1
    return delivered


@app.post("/api/nodes/{node_id}/messages")
async def send_message_to_node(node_id: int, request: Request):
    body = await request.json()
    payload = body.get("payload")
    if payload is None:
        raise HTTPException(status_code=400, detail="payload is required")
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    msg_type = body.get("type", "message")
    from_node_id = body.get("from_node_id")

    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    msg_id = db.create_message(from_node_id, node_id, msg_type, payload)
    if node.status == AgentStatus.IDLE.value:
        _deliver_pending_messages(node)
    await _broadcast_tree()
    msg = db.get_message(msg_id)
    return JSONResponse(msg.as_dict() if msg else {"id": msg_id}, status_code=201)


@app.get("/api/nodes/{node_id}/messages")
def get_node_messages(node_id: int, status: str = "pending", limit: int = 50):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    messages = db.get_messages_for_node(node_id, status=status, limit=limit)
    return JSONResponse([m.as_dict() for m in messages])


@app.patch("/api/messages/{message_id}")
async def update_message(message_id: int, request: Request):
    body = await request.json()
    new_status = body.get("status")
    if new_status not in ("done",):
        raise HTTPException(status_code=400, detail="status must be 'done'")
    msg = db.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    ok = db.mark_message_done(message_id)
    if not ok:
        raise HTTPException(status_code=409, detail="Message cannot be marked done in its current state")
    return JSONResponse({"ok": True})


@app.post("/api/nodes/{node_id}/broadcast")
async def broadcast_to_children(node_id: int, request: Request):
    body = await request.json()
    payload = body.get("payload")
    if payload is None:
        raise HTTPException(status_code=400, detail="payload is required")
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    msg_type = body.get("type", "message")

    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    msg_ids = db.create_broadcast(node_id, msg_type, payload)
    children = db.get_node_children(node_id)
    for child in children:
        if child.status == AgentStatus.IDLE.value:
            _deliver_pending_messages(child)
    await _broadcast_tree()
    return JSONResponse({"ok": True, "messages_created": len(msg_ids), "message_ids": msg_ids}, status_code=201)


@app.post("/api/queue")
async def post_to_queue(request: Request):
    body = await request.json()
    payload = body.get("payload")
    if payload is None:
        raise HTTPException(status_code=400, detail="payload is required")
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    msg_type = body.get("type", "task")
    from_node_id = body.get("from_node_id")

    msg_id = db.create_message(from_node_id, None, msg_type, payload)
    msg = db.get_message(msg_id)
    return JSONResponse(msg.as_dict() if msg else {"id": msg_id}, status_code=201)


@app.get("/api/queue")
def list_queue(status: str = "pending", limit: int = 50):
    tasks = db.get_queue_tasks(status=status, limit=limit)
    return JSONResponse([t.as_dict() for t in tasks])


@app.post("/api/queue/{message_id}/claim")
async def claim_queue_task(message_id: int, request: Request):
    body = await request.json()
    node_id = body.get("node_id")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")
    expires = body.get("expires_minutes", 10)

    msg = db.get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Task not found")
    if msg.to_node_id is not None:
        raise HTTPException(status_code=400, detail="Not a queue task")

    ok = db.claim_queue_task(message_id, node_id, expires)
    if not ok:
        raise HTTPException(status_code=409, detail="Task already claimed")
    msg = db.get_message(message_id)
    return JSONResponse(msg.as_dict() if msg else {"ok": True})


# --- Project Labels ---

@app.get("/api/project-labels")
def list_project_labels():
    labels = db.list_project_labels()
    return JSONResponse([{"id": lb.id, "name": lb.name, "path": lb.path} for lb in labels])


@app.post("/api/project-labels")
async def create_project_label(request: Request):
    body = await request.json()
    label_id = body.get("id", "").strip()
    name = body.get("name", "").strip()
    path = body.get("path", "").strip()

    if not label_id or not name:
        raise HTTPException(status_code=400, detail="id and name are required")
    if not path:
        path = os.getcwd()

    try:
        db.add_project_label(label_id, name, os.path.abspath(path))
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
    label = next((lb for lb in labels if lb.id == label_id), None)
    if not label:
        raise HTTPException(status_code=404, detail="Project not found")

    is_dir = os.path.isdir(label.path)
    skills = list_project_skills(label.path)["skills"] if is_dir else []
    nodes = db.get_nodes_by_project_label_id(label_id)
    plugins = list_project_plugins(label.path)["plugins"] if is_dir else []
    hooks = list_project_hooks(label.path)["hooks"] if is_dir else []
    configs = get_project_config(label.path)["configs"] if is_dir else {}
    git = get_project_git_info(label.path)["git"] if is_dir else {}

    return JSONResponse({
        "label": {"id": label.id, "name": label.name, "path": label.path},
        "skills": skills,
        "nodes": [n.as_summary() for n in nodes],
        "plugins": plugins,
        "hooks": hooks,
        "configs": configs,
        "git": git,
    })


@app.get("/api/agent-types")
def available_agent_types():
    """Return available agent types based on installed binaries."""
    types = [
        {"id": "opencode", "label": "Open Code", "available": shutil.which("opencode") is not None},
        {"id": "claude", "label": "Claude Code", "available": shutil.which("claude") is not None},
        {"id": "aap_opencode", "label": "AAP + Open Code", "available": shutil.which("aap") is not None and shutil.which("opencode") is not None},
        {"id": "aap_claude", "label": "AAP + Claude Code", "available": shutil.which("aap") is not None and shutil.which("claude") is not None},
        {"id": "bash", "label": "Bash", "available": True},
    ]
    return JSONResponse(types)


@app.get("/api/skills")
def global_skills():
    return JSONResponse(list_project_skills(os.path.expanduser("~")))


# --- Extensions Manager ---

@app.get("/api/extensions")
def list_extensions():  # pragma: no cover
    """List all extensions and which projects have them installed (filesystem scan)."""
    from pathlib import Path
    repo_root = Path(__file__).parent.parent
    source_skills = repo_root / "skills"
    source_hooks = repo_root / "armada_ai" / "hooks"
    source_plugins = repo_root / ".opencode" / "plugins"

    extensions = []

    if source_skills.is_dir():
        for d in sorted(source_skills.iterdir()):
            if not d.is_dir():
                continue
            md = d / "SKILL.md"
            if not md.is_file():
                continue
            desc = ""
            try:
                for line in md.read_text().split("\n"):
                    s = line.strip()
                    if s and not s.startswith("#") and not s.startswith(">") and len(s) > 5:
                        desc = s[:200]
                        break
            except Exception:
                pass
            extensions.append({"id": d.name, "type": "skill", "name": d.name, "description": desc, "agent": "both"})

    if source_hooks.is_dir():
        for f in sorted(source_hooks.iterdir()):
            if not f.is_file() or not f.name.endswith(".sh"):
                continue
            ext_id = f"hook-{f.stem}"
            desc = ""
            try:
                for line in f.read_text().split("\n"):
                    s = line.strip()
                    if s.startswith("# ") and len(s) > 8 and "!/" not in s:
                        desc = s.lstrip("# ").strip()[:200]
                        break
            except Exception:
                pass
            extensions.append({"id": ext_id, "type": "hook", "name": f.name, "description": desc, "agent": "claude"})

    if source_plugins.is_dir():
        for f in sorted(source_plugins.iterdir()):
            if not f.is_file():
                continue
            ext_id = f"plugin-{f.stem}"
            extensions.append({"id": ext_id, "type": "plugin", "name": f.name, "description": "", "agent": "opencode"})

    # Scan MCP configs from project root and global
    mcp_seen = set()
    for candidate in (
        repo_root / ".opencode" / "mcp.json",
        repo_root / ".claude" / "mcp.json",
        repo_root / ".opencode" / "mcp.jsonc",
        Path.home() / ".config" / "opencode" / "mcp.json",
        Path.home() / ".claude" / "mcp.json",
    ):
        if candidate.is_file() and candidate.name not in mcp_seen:
            mcp_seen.add(candidate.name)
            desc = ""
            try:
                data = json.loads(candidate.read_text())
                servers = data.get("mcpServers", {})
                desc = ", ".join(list(servers.keys())[:3]) or "MCP config"
            except Exception:
                desc = "MCP config"
            ext_id = f"mcp-{candidate.stem}"
            mcp_agent = "opencode" if "opencode" in str(candidate) else "claude" if ".claude" in str(candidate) else "both"
            extensions.append({"id": ext_id, "type": "mcp", "name": str(candidate.relative_to(candidate.parent.parent)) if candidate.parent.parent else candidate.name, "description": desc, "agent": mcp_agent})

    # Scan custom extensions from ~/.armada/extensions/
    custom_dir = Path.home() / ".armada" / "extensions"
    for sub in ("skills", "hooks", "plugins", "mcp"):
        sub_path = custom_dir / sub
        if not sub_path.is_dir():
            continue
        for entry in sorted(sub_path.iterdir()):
            if sub == "skills" and entry.is_dir():
                md = entry / "SKILL.md"
                if md.is_file():
                    ext_id = f"custom-{entry.name}"
                    desc = ""
                    try:
                        for line in md.read_text().split("\n"):
                            s = line.strip()
                            if s and not s.startswith("#") and not s.startswith(">") and len(s) > 5:
                                desc = s[:200]
                                break
                    except Exception:
                        pass
                    extensions.append({"id": ext_id, "type": "skill", "name": entry.name, "description": desc, "source": "custom", "agent": "both"})
            elif sub == "hooks" and entry.is_file() and entry.name.endswith(".sh"):
                ext_id = f"custom-hook-{entry.stem}"
                extensions.append({"id": ext_id, "type": "hook", "name": entry.name, "description": "Custom hook", "source": "custom", "agent": "claude"})
            elif sub == "plugins" and entry.is_file():
                ext_id = f"custom-plugin-{entry.stem}"
                extensions.append({"id": ext_id, "type": "plugin", "name": entry.name, "description": "Custom plugin", "source": "custom", "agent": "opencode"})
            elif sub == "mcp" and entry.is_file() and entry.name.endswith(".json"):
                ext_id = f"custom-mcp-{entry.stem}"
                extensions.append({"id": ext_id, "type": "mcp", "name": entry.name, "description": "Custom MCP", "source": "custom", "agent": "both"})

    labels = db.list_project_labels()
    for ext in extensions:
        ext["projects"] = []
        for lb in labels:
            if not os.path.isdir(lb.path):
                continue
            installed = False
            if ext["type"] == "skill":
                for agent in ("opencode", "claude"):
                    skill_path = Path(lb.path) / f".{agent}" / "skills" / ext["id"] / "SKILL.md"
                    if skill_path.exists():
                        installed = True
                        break
            elif ext["type"] == "hook":
                hook_path = Path(lb.path) / ".claude" / "hooks" / ext["name"]
                if hook_path.exists():
                    installed = True
            elif ext["type"] == "plugin":
                for suffix in (".ts", ".js"):
                    plugin_path = Path(lb.path) / ".opencode" / "plugins" / ext["name"]
                    alt_path = Path(lb.path) / ".opencode" / "plugin" / ext["name"]
                    if plugin_path.exists() or alt_path.exists():
                        installed = True
                        break
            elif ext["type"] == "mcp":
                for agent in ("opencode", "claude"):
                    mcp_path = Path(lb.path) / f".{agent}" / "mcp.json"
                    if mcp_path.exists():
                        installed = True
                        break
            if installed:
                ext["projects"].append({"id": lb.id, "name": lb.name, "path": lb.path})

    return JSONResponse(extensions)


@app.get("/api/extensions/{extension_id}/content")
def extension_content(extension_id: str):
    from pathlib import Path
    repo_root = Path(__file__).parent.parent
    paths = []
    if extension_id.startswith("custom-mcp-"):
        paths.append(Path.home() / ".armada" / "extensions" / "mcp" / f"{extension_id[11:]}.json")
    elif extension_id.startswith("custom-hook-"):
        paths.append(Path.home() / ".armada" / "extensions" / "hooks" / f"{extension_id[12:]}.sh")
    elif extension_id.startswith("custom-plugin-"):
        paths.append(Path.home() / ".armada" / "extensions" / "plugins" / f"{extension_id[14:]}")
    elif extension_id.startswith("custom-"):
        paths.append(Path.home() / ".armada" / "extensions" / "skills" / extension_id[7:] / "SKILL.md")
    elif extension_id.startswith("hook-"):
        paths.append(repo_root / "armada_ai" / "hooks" / f"{extension_id[5:]}.sh")
    elif extension_id.startswith("plugin-"):
        for suffix in (".ts", ".js"):
            p = repo_root / ".opencode" / "plugins" / f"{extension_id[7:]}{suffix}"
            if p.exists():
                paths.append(p)
    else:
        paths.append(repo_root / "skills" / extension_id / "SKILL.md")
    for p in paths:
        if p.exists():
            try:
                return JSONResponse({"id": extension_id, "path": str(p), "content": p.read_text()})
            except Exception:
                raise HTTPException(status_code=500, detail="Failed to read file")
    raise HTTPException(status_code=404, detail="Extension file not found")


@app.post("/api/extensions/install")
async def install_extension_endpoint(request: Request):  # pragma: no cover
    """Copy an extension's file(s) into a project directory."""
    import shutil
    from pathlib import Path as _Path

    body = await request.json()
    extension_id = body.get("extension_id")
    project_label_id = body.get("project_label_id")

    if not extension_id or not project_label_id:
        raise HTTPException(status_code=400, detail="extension_id and project_label_id are required")

    project_path = db.get_project_label_path(project_label_id)
    if not project_path or not os.path.isdir(project_path):
        raise HTTPException(status_code=400, detail="Project not found or path does not exist")

    repo_root = _Path(__file__).parent.parent
    target = _Path(project_path)
    copied = []

    if extension_id.startswith("hook-"):
        hook_name = extension_id[5:].removeprefix("custom-")
        src = repo_root / "armada_ai" / "hooks" / f"{hook_name}.sh"
        if not src.exists():
            src = _Path.home() / ".armada" / "extensions" / "hooks" / f"{hook_name}.sh"
        if src.exists():
            dst_dir = target / ".claude" / "hooks"
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f"{hook_name}.sh"
            shutil.copy2(src, dst)
            dst.chmod(0o755)
            copied.append(str(dst))

    elif extension_id.startswith("plugin-"):
        plugin_name = extension_id[7:].removeprefix("custom-")
        dst_dir = target / ".opencode" / "plugins"
        dst_dir.mkdir(parents=True, exist_ok=True)
        for suffix in (".ts", ".js"):
            src = repo_root / ".opencode" / "plugins" / f"{plugin_name}{suffix}"
            if not src.exists():
                src = _Path.home() / ".armada" / "extensions" / "plugins" / f"{plugin_name}{suffix}"
            if src.exists():
                dst = dst_dir / f"{plugin_name}{suffix}"
                shutil.copy2(src, dst)
                copied.append(str(dst))

    elif extension_id.startswith("mcp-"):
        mcp_name = extension_id.removeprefix("mcp-").removeprefix("custom-")
        src = repo_root / ".opencode" / f"{mcp_name}.json"
        alt = repo_root / ".claude" / f"{mcp_name}.json"
        if not src.exists() and not alt.exists():
            src = _Path.home() / ".armada" / "extensions" / "mcp" / f"{mcp_name}.json"
        for s in (src, alt):
            if s.exists():
                for agent_dir in (".opencode", ".claude"):
                    dst_dir = target / agent_dir
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    dst = dst_dir / "mcp.json"
                    shutil.copy2(s, dst)
                    copied.append(str(dst))

    else:
        skill_name = extension_id.removeprefix("custom-")
        src = repo_root / "skills" / skill_name / "SKILL.md"
        if not src.exists():
            src = _Path.home() / ".armada" / "extensions" / "skills" / skill_name / "SKILL.md"
        if src.exists():
            for agent_dir in (".opencode", ".claude"):
                dst_dir = target / agent_dir / "skills" / skill_name
                dst_dir.mkdir(parents=True, exist_ok=True)
                dst = dst_dir / "SKILL.md"
                shutil.copy2(src, dst)
                copied.append(str(dst))

    if not copied:
        raise HTTPException(status_code=404, detail="Extension source file not found")

    return JSONResponse({"ok": True, "copied": copied})


@app.post("/api/extensions/create")
async def create_extension_endpoint(request: Request):  # pragma: no cover
    """Save a custom extension to ~/.armada/extensions/."""
    from pathlib import Path as _Path

    body = await request.json()
    ext_type = body.get("type", "skill")
    name = body.get("name", "").strip()
    code = body.get("code", "").strip()

    if not name or not code:
        raise HTTPException(status_code=400, detail="name and code are required")
    if ext_type not in ("skill", "hook", "plugin", "mcp"):
        raise HTTPException(status_code=400, detail="type must be skill, hook, plugin, or mcp")

    ext_dir = _Path.home() / ".armada" / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)

    if ext_type == "skill":
        dst = ext_dir / "skills" / name / "SKILL.md"
    elif ext_type == "hook":
        dst = ext_dir / "hooks" / f"{name}.sh"
    elif ext_type == "mcp":
        dst = ext_dir / "mcp" / f"{name}.json"
    else:
        dst = ext_dir / "plugins" / f"{name}.ts"

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(code)

    return JSONResponse({"ok": True, "path": str(dst)})


# --- Maintenance ---

@app.post("/api/refresh-hooks")
def refresh_hooks():
    labels = db.list_project_labels()
    updated = []
    skipped = []
    failed = []
    for label in labels:
        if not os.path.isdir(label.path):
            skipped.append({"id": label.id, "name": label.name, "reason": "directory missing"})
            continue
        try:
            deployment.install_skills_to_project(label.path)
            deployment.deploy_claude_hooks(label.path)
            updated.append(label.id)
        except Exception as e:
            failed.append({"id": label.id, "name": label.name, "reason": str(e)})
    return JSONResponse({
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    })


# --- Agent Report ---

@app.post("/api/report")
async def agent_report(request: Request):
    body = await request.json()
    report = AgentReportRequest(
        name=body.get("name"),
        status=body.get("status", "idle"),
        message=body.get("message"),
        tokens=body.get("tokens"),
        cost=body.get("cost"),
        client_ts=body.get("_client_ts") or 0,
    )

    validation_error = report.validate()
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    node = db.get_node_by_name(report.name)
    if not node:
        raise HTTPException(status_code=404, detail=f"Unknown node: {report.name}")

    options_json = json.dumps(body.get("options", [])) if body.get("options") else ""
    db.add_status_report(node.id, report.status, report.message, options=options_json)
    logs.log_report(report.name, report.status, report.message)
    metrics.counter_inc("armada_reports_total")

    report_latency = _time.time() - report.client_ts
    if 0 < report_latency < 3600:
        metrics.histogram_observe("armada_report_latency_seconds", report_latency)

    if report.status == AgentStatus.ERROR.value:
        metrics.counter_inc("armada_errors_total")

    if report.tokens or report.cost:
        db.accumulate_cost(
            node.id,
            tokens_in=report.tokens.get("input", 0) if report.tokens else 0,
            tokens_out=report.tokens.get("output", 0) if report.tokens else 0,
            cost=report.cost or 0.0,
        )
        if report.tokens:
            metrics.counter_inc("armada_tokens_total",
                                report.tokens.get("input", 0), ("input",))
            metrics.counter_inc("armada_tokens_total",
                                report.tokens.get("output", 0), ("output",))

    await _broadcast_tree()
    if report.status == AgentStatus.IDLE.value:
        _deliver_pending_messages(node)
    return JSONResponse({"ok": True})
# --- Logs ---

_SAFE_LOG_NAME = re.compile(r'^[a-zA-Z0-9_][-a-zA-Z0-9_]*$')


@app.get("/api/logs/{node_name}")
def get_node_logs(node_name: str, limit: int = 50, before: float | None = None):
    if not _SAFE_LOG_NAME.match(node_name):
        raise HTTPException(status_code=400, detail="Invalid node name")
    node = db.get_node_by_name(node_name)
    if not node and node_name not in db.existing_names() and node_name != "_server":
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
    return JSONResponse({
        "count": len(entries), "entries": entries,
        "path": os.path.join(constants.LOGS_DIR, "_server.jsonl"),
    })


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
    active = sum(1 for n in nodes if n.status == "active")
    pending = sum(1 for n in nodes if n.status == "pending")
    idle = sum(1 for n in nodes if n.status == "idle")
    metrics.gauge_set("armada_agents", active, ("active",))
    metrics.gauge_set("armada_agents", pending, ("pending",))
    metrics.gauge_set("armada_agents", idle, ("idle",))
    return JSONResponse({
        "status": "ok",
        "agents": len(nodes),
        "active": active, "pending": pending, "idle": idle,
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
        s = n.status
        if s in statuses:
            statuses[s] += 1
    for s, count in statuses.items():
        metrics.gauge_set("armada_agents", count, (s,))
    total_cost = sum(n.total_cost for n in nodes)
    metrics.gauge_set("armada_cost_total", total_cost)
    return Response(content=metrics.generate_latest(), media_type="text/plain; charset=utf-8")


@app.get("/api/stats/summary")
def stats_summary():
    return JSONResponse(db.get_stats_summary())


@app.get("/api/stats/history")
def stats_history(hours: int = 24):
    return JSONResponse(db.get_hourly_stats(hours))


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
    token = TokenManager.extract_from_request(request)
    return JSONResponse({
        "valid": bool(token and token == TOKEN),
        "has_token": bool(TOKEN),
        "server_alive": True,
        "uptime": round(_time.time() - SERVER_START_TS, 1) if SERVER_START_TS else 0,
    })


# --- Daemon ---

PID_FILE = constants.PID_FILE


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


def start_server(daemon: bool = True, open_browser: bool = True,
                 lan: bool = False, keep_token: bool = True):
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
