import os
import sys
import subprocess
import threading
import re
import secrets
import socket
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from . import db
from . import naming
from . import tmux
from . import health

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

app = FastAPI(title="Armada")
TEMPLATE_DIR = Path(__file__).parent / "templates"
PID_FILE = os.path.expanduser("~/.armada/server.pid")
TOKEN_FILE = os.path.expanduser("~/.armada/token")
HOST = "127.0.0.1"
PORT = 9100

TOKEN = ""


def _ensure_token():
    global TOKEN
    if not TOKEN:
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
    if path.startswith("/api/") and path not in ("/api/report", "/api/auth/status"):
        if not _check_token(request):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
def startup():
    db.init_db()
    try:
        tmux.ensure_armada_session()
    except RuntimeError:
        pass
    health.start_health_loop()


# --- Dashboard ---

@app.get("/", response_class=HTMLResponse)
def dashboard_page():
    html_path = TEMPLATE_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text()
    return HTMLResponse("<h1>Dashboard not found</h1>")


# --- Tree & Nodes ---

@app.get("/api/tree")
def get_tree(hide_dead: bool = False):
    return JSONResponse(db.build_tree(include_dead=not hide_dead))


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

    existing_names = db.existing_names()

    if name and name in existing_names:
        raise HTTPException(status_code=409, detail=f"Node '{name}' already exists")

    if project_label_id:
        path = db.get_project_label_path(project_label_id)
        if not path:
            raise HTTPException(status_code=400, detail="Project label not found")
        if not os.path.isdir(path):
            raise HTTPException(status_code=400,
                detail=f"Project path does not exist: {path}")
        working_dir = path
    else:
        working_dir = os.path.expanduser("~")

    if parent_id:
        parent = db.get_node(parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent node not found")

    colour = naming.next_colour(db.active_colours())
    agent_name = name or naming.generate_name(existing_names)

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
    tmux.save_agent_hook(agent_name)

    if initial_prompt:
        delay = 8.0 if agent_type in ("opencode", "claude") else 3.0
        tmux.send_initial_prompt(agent_name, initial_prompt, delay=delay)

    node = db.get_node(node_id)
    return JSONResponse(node, status_code=201)


@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    killed = db.kill_node(node_id)
    for entry in killed:
        try:
            tmux.kill_node_window(entry["name"])
        except Exception:
            pass

    return JSONResponse({"ok": True, "killed": len(killed)})


@app.post("/api/nodes/{node_id}/send")
async def send_to_node(node_id: int, request: Request):
    body = await request.json()
    command = body.get("command", "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")

    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if node.get("status") == "dead":
        raise HTTPException(status_code=410, detail="Node is dead")

    if not tmux.window_exists(node["name"]):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    ok = tmux.send_keys(node["name"], command)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send command")

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
        return JSONResponse({"ok": True, "hidden": len(hidden)})
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

    return JSONResponse({"ok": True})


@app.get("/api/nodes/{node_id}/terminal")
def terminal_view(node_id: int):
    node = db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not tmux.window_exists(node["name"]):
        raise HTTPException(status_code=410, detail="Node window no longer exists")

    target = f"armada:{node['name']}"

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
    text = ''.join(line.ljust(cols) for line in text_lines)
    return JSONResponse({"text": text, "cols": cols, "rows": rows})


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


# --- Maintenance ---

@app.post("/api/refresh-hooks")
def refresh_hooks():
    """Re-deploy skills and hooks to all project label paths."""
    labels = db.list_project_labels()
    updated = []
    for label in labels:
        path = label["path"]
        if not os.path.isdir(path):
            continue
        try:
            tmux.install_skills(path)
            tmux._deploy_claude_hooks(path)
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

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if status not in ("active", "idle", "error", "pending"):
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    node = db.get_node_by_name(name)
    if not node:
        raise HTTPException(status_code=404, detail=f"Unknown node: {name}")

    db.add_status_report(node["id"], status, message)
    return JSONResponse({"ok": True})


# --- Auth ---

@app.get("/api/auth/status")
def auth_status(request: Request):
    token = request.query_params.get("token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    return JSONResponse({"valid": token == TOKEN, "has_token": bool(TOKEN)})


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


def start_server(daemon: bool = True, open_browser: bool = True, lan: bool = False):
    host = "0.0.0.0" if lan else HOST
    token = _ensure_token()

    if daemon:
        _daemonize()

    if open_browser and not lan:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{PORT}?token={token}")).start()

    try:
        uvicorn.run(app, host=host, port=PORT, log_level="warning")
    finally:
        _remove_pid()
