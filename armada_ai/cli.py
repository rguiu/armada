import os
import sys
import signal
import socket
import subprocess
import platform

from . import constants


def _read_token():
    try:
        return open(constants.TOKEN_FILE).read().strip()
    except FileNotFoundError:
        return ""


def _hyperlink(url: str, text: str | None = None) -> str:
    if text is None:
        text = url
    return f"\033]8;;{url}\007{text}\033]8;;\007"


def _get_pid_from_port(port: int = constants.DEFAULT_PORT) -> int | None:
    system = platform.system()
    try:
        if system == "Darwin":
            result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split("\n")[0])
        elif system == "Linux":
            result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
            for line in result.stdout.split("\n"):
                if f":{port}" in line:
                    pid_str = line.split("pid=")[-1].split(",")[0].strip()
                    if pid_str.isdigit():
                        return int(pid_str)
            result = subprocess.run(["fuser", f"{port}/tcp"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split()[-1])
    except Exception:
        pass
    return None


def _get_db_lock_pids(db_path: str, current_pid: int | None = None) -> list[int]:
    system = platform.system()
    pids = []
    try:
        if system == "Darwin":
            result = subprocess.run(["fuser", db_path], capture_output=True, text=True)
            if result.returncode == 0:
                for p in result.stdout.split():
                    if p.strip().isdigit():
                        pid = int(p)
                        if pid != current_pid and pid != os.getpid():
                            pids.append(pid)
        elif system == "Linux":
            result = subprocess.run(["fuser", db_path], capture_output=True, text=True)
            if result.returncode == 0:
                for p in result.stdout.split():
                    if p.strip().isdigit():
                        pid = int(p)
                        if pid != current_pid and pid != os.getpid():
                            pids.append(pid)
    except Exception:
        pass
    return pids


def main():
    args = sys.argv[1:]
    lan = "--lan" in args
    qr = "--qr" in args
    no_browser = "--no-browser" in args
    keep_token = "--keep-token" in args or "--no-token-rotate" in args
    flags = ("--lan", "--qr", "--keep-token", "--no-token-rotate", "--no-browser")
    args = [a for a in args if a not in flags]

    if not args or args[0] in ("start", "serve"):
        from .server import start_server, _ensure_token
        _ensure_token(keep=True)
        _print_startup_info(lan=lan, qr=qr)
        start_server(daemon=True, open_browser=not no_browser, lan=lan, keep_token=keep_token)

    elif args[0] == "stop":
        _stop_server()

    elif args[0] == "attach":
        do_split = "--split" in args
        node_arg = next((a for a in args[1:] if not a.startswith("--")), None)
        if do_split and node_arg:
            _attach_split(node_arg)
        elif node_arg:
            _attach_node(node_arg)
        else:
            from .server import start_server, _ensure_token
            _ensure_token(keep=True)
            _print_startup_info(lan=lan, qr=qr)
            start_server(daemon=False, open_browser=False, lan=lan)

    elif args[0] == "setup":
        _setup_skills()

    elif args[0] == "version":
        print(f"armada {constants.VERSION}")

    elif args[0] == "token":
        _print_token(qr=qr, lan=lan)

    elif args[0] == "doctor":
        nuke = "--nuke" in args
        _doctor(nuke=nuke)

    elif args[0] == "status":
        _status()

    elif args[0] == "config":
        _config(args[1:])

    elif args[0] == "service":
        _service_cmd(args[1:])

    elif args[0] in ("nodes", "list"):
        _nodes_cmd(args[1:])

    elif args[0] == "create":
        _create_cmd(args[1:])

    elif args[0] == "projects":
        _projects_cmd(args[1:])

    elif args[0] == "watch":
        _watch_cmd(args[1:])

    elif args[0] == "demodb":
        _demodb_cmd(args[1:])

    elif args[0] == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()

    elif args[0] == "report":
        _report_cmd(args[1:])

    else:
        print("Usage: armada [start|stop|attach|setup|version|token|doctor|status|config|service|nodes|demodb|watch|mcp|report] [--lan] [--qr] [--keep-token]")
        print("  start        Start the Armada server daemon + open dashboard")
        print("  stop         Stop the Armada server")
        print("  attach       Attach to a node: armada attach <name> [--split] (no args = debug mode)")
        print("  setup        Install Armada skills to user profile")
        print("  version      Print the Armada version")
        print("  token        Print the auth token (--qr for scannable QR code)")
        print("  doctor       Clean up orphaned tmux sessions and stale state")
        print("  status       Show server and node status")
        print("  config       Show or manage configuration (~/.armada/config.yaml)")
        print("  service      Install as system service (launchd/systemd)")
        print("  nodes        List all agents in a table")
        print("  create       Create a new agent node")
        print("  projects     List, add, or remove projects")
        print("  demodb       Seed a demo database for screen recordings")
        print("  watch        Interactive live dashboard with select, attach, and alerts")
        print("  mcp          Start the Armada MCP server (stdio mode, for AI agents)")
        print("  report       Report node status: armada report <status> <message> [--options '<json>']")
        print("  --lan        Bind to / use LAN IP (for other devices on network)")
        print("  --qr         Show QR code (with token command)")
        print("  --no-browser Don't open the dashboard in a browser")
        print("  --keep-token Reuse existing token (don't regenerate on restart)")
        print("  --nuke       (with doctor) Kill ALL armada tmux sessions and reset DB")
        print()
        print("  The dashboard opens in your default browser automatically.")
        print("  URLs are printed as clickable hyperlinks (OSC 8).")
        sys.exit(1)


def _lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _print_startup_info(lan: bool = False, qr: bool = False):
    token = _read_token()
    if not token:
        return

    local_url = f"http://127.0.0.1:9100?token={token}"
    print(f"\n{_hyperlink(local_url)}")
    if lan:
        ip = _lan_ip()
        print(_hyperlink(f"http://{ip}:9100?token={token}"))
    print()

    if qr:
        import qrcode
        url = f"http://{_lan_ip()}:9100?token={token}" if lan else local_url
        qr_code = qrcode.QRCode()
        qr_code.add_data(url)
        qr_code.print_ascii()
        print()


def _print_token(qr: bool = False, lan: bool = False):
    token = _read_token()
    if not token:
        print("No token found. Start Armada first with: armada start", file=sys.stderr)
        sys.exit(1)

    if qr:
        import qrcode
        host = _lan_ip() if lan else "127.0.0.1"
        url = f"http://{host}:9100?token={token}"
        print(_hyperlink(url))
        print()
        qr_code = qrcode.QRCode()
        qr_code.add_data(url)
        qr_code.print_ascii()
        print()
    else:
        print(token)


def _stop_server():
    pid_file = os.path.expanduser("~/.armada/server.pid")
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Armada server (PID {pid}).")
        return
    except FileNotFoundError:
        pass
    except ProcessLookupError:
        try:
            os.remove(pid_file)
        except OSError:
            pass

    found_pid = _get_pid_from_port(constants.DEFAULT_PORT)
    if found_pid:
        try:
            os.kill(found_pid, signal.SIGTERM)
            print(f"Stopped Armada server (PID {found_pid}, found via port).")
        except ProcessLookupError:
            pass


def _service_cmd(subargs: list[str]):
    from . import service
    if not subargs or subargs[0] == "install":
        service.install()
    else:
        print("Usage: armada service install")
        print("  Install Armada as a system service (launchd on macOS, systemd on Linux)")
        print("  The server will start on login and restart automatically on crash.")


def _config(subargs: list[str]):
    from . import config
    if not subargs:
        cfg = config.get_all()
        for key, value in cfg.items():
            if isinstance(value, list):
                print(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            print(f"  - {k}: {v}")
                    else:
                        print(f"  - {item}")
            else:
                print(f"{key}: {value}")
    elif subargs[0] == "init":
        config.init_config()
        print(f"Config initialized at {config.CONFIG_PATH}")
    elif subargs[0] == "set" and len(subargs) >= 3:
        key = subargs[1]
        val_str = " ".join(subargs[2:])
        cfg = config.get_all()
        valid_keys = config.DEFAULTS.keys()
        if key not in valid_keys:
            print(f"Unknown key: {key}. Valid keys: {', '.join(valid_keys)}", file=sys.stderr)
            sys.exit(1)
        default_value = config.DEFAULTS[key]
        if isinstance(default_value, bool):
            cfg[key] = val_str.lower() in ("true", "1", "yes")
        elif isinstance(default_value, int):
            try:
                cfg[key] = int(val_str)
            except ValueError:
                print(f"Invalid integer: {val_str}", file=sys.stderr)
                sys.exit(1)
        elif isinstance(default_value, float):
            try:
                cfg[key] = float(val_str)
            except ValueError:
                print(f"Invalid float: {val_str}", file=sys.stderr)
                sys.exit(1)
        else:
            cfg[key] = val_str
        config.write_config(cfg)
        print(f"{key} = {cfg[key]}")
    else:
        print("Usage: armada config [init|show|set <key> <value>]")
        print("  armada config              Show current configuration")
        print("  armada config init          Create default config file")
        print("  armada config set <key> <v> Set a config value")
        print(f"\nConfig file: {config.CONFIG_PATH}")


def _setup_skills():
    from . import tmux

    skill_dir = os.path.join(os.path.dirname(__file__), "..", "skills")
    if not os.path.isdir(skill_dir):
        print("Skills directory not found. Run from the armada repo root.", file=sys.stderr)
        sys.exit(1)

    skill_dir = os.path.abspath(skill_dir)
    print(f"Installing skills from {skill_dir}...")

    token = _read_token()

    if token:
        os.environ["ARMADA_AUTH_TOKEN"] = token
        print("  ARMADA_AUTH_TOKEN set")

    installed = tmux.install_skills(skill_dir)
    print(f"  {installed} file(s) installed")

    claude_hooks = os.path.expanduser("~/.claude/hooks")
    if os.path.isdir(claude_hooks):
        tmux.deploy_claude_hooks(skill_dir)
        print(f"  Claude Code hooks deployed to {claude_hooks}")
    else:
        print("  Claude Code hooks directory not found (skip)")


def _status():
    import json
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:9100/health")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        print(f"Armada server: running (v{data.get('version','?')})")
        print(f"Uptime: {data.get('uptime',0):.0f}s")
        print(f"Agents: {data.get('agents',0)} (active={data.get('active',0)} pending={data.get('pending',0)} idle={data.get('idle',0)})")
    except Exception:
        print("Armada server: not reachable")



def _doctor(nuke: bool = False):
    import sqlite3
    import glob
    from . import tmux as _tmux_mod

    print("Armada Doctor\n")

    # 1. Check tmux
    print("[1] Tmux sessions")
    try:
        running = _tmux_mod.running_window_names()
        if running:
            print(f"  Live windows: {', '.join(running)}")
        else:
            print("  No armada windows found")
    except Exception as e:
        print(f"  Error checking tmux: {e}")

    # 2. Check server
    print("\n[2] Server process")
    found_pid = _get_pid_from_port(constants.DEFAULT_PORT)
    pid_file = os.path.expanduser("~/.armada/server.pid")
    pid_file_pid = None
    try:
        with open(pid_file) as f:
            pid_file_pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        pass

    if found_pid:
        print(f"  Listening on port {constants.DEFAULT_PORT} (PID {found_pid})")
    elif pid_file_pid:
        try:
            os.kill(pid_file_pid, 0)
            print(f"  PID file says {pid_file_pid} (but not on port {constants.DEFAULT_PORT})")
        except OSError:
            print(f"  PID file says {pid_file_pid} (process is dead — cleaning up)")
            os.remove(pid_file)
    else:
        print("  Not running")

    if nuke:
        print("\n--nuke: Killing all armada tmux sessions and resetting state...")
        try:
            result = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for session in result.stdout.strip().split("\n"):
                    if session.startswith("armada"):
                        subprocess.run(["tmux", "kill-session", "-t", session],
                                       capture_output=True, timeout=5)
                        print(f"  Killed session: {session}")
        except Exception:
            pass
        db_path = constants.DB_PATH
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"  Removed {os.path.basename(db_path)}")
        if os.path.exists(pid_file):
            os.remove(pid_file)
            print("  Removed PID file")
        log_dir = os.path.expanduser("~/.armada/logs")
        if os.path.isdir(log_dir):
            for f in os.listdir(log_dir):
                os.remove(os.path.join(log_dir, f))
            print("  Cleared logs")
        print("\nDone. Start fresh with: armada")
        sys.exit(0)

    # 3. Sync DB with tmux
    print("\n[3] Database sync")
    db_path = constants.DB_PATH
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        live_nodes = conn.execute(
            "SELECT id, name FROM nodes WHERE status != 'dead'"
        ).fetchall()
        running_names = _tmux_mod.running_window_names() if 'running' in dir() else []
        stale = [(row["id"], row["name"]) for row in live_nodes if row["name"] not in running_names]
        if stale:
            for nid, name in stale:
                conn.execute(
                    "UPDATE nodes SET status='dead' WHERE id=?",
                    (nid,)
                )
            conn.commit()
            print(f"  Marked {len(stale)} node(s) as dead: {', '.join(n for _, n in stale)}")
        else:
            print("  All DB nodes have live tmux windows")
        conn.close()
    else:
        print("  No DB found (nothing to sync)")

    # 4. Clean up /tmp/_armada_* temp files
    print("\n[4] Temp files (/tmp/_armada_*)")
    temps = glob.glob("/tmp/_armada_*")
    if temps:
        for f in temps:
            try:
                os.remove(f)
            except OSError:
                pass
        print(f"  Removed {len(temps)} file(s)")
    else:
        print("  None found")

    # 5. Clean up stale hooks
    print("\n[5] Stale hook files")
    hooks_dir = os.path.expanduser("~/.armada/hooks")
    if os.path.isdir(hooks_dir):
        running = _tmux_mod.running_window_names()
        removed = 0
        for hook_file in os.listdir(hooks_dir):
            if hook_file.endswith(".md"):
                node_name = hook_file[:-3]
                if node_name not in running:
                    os.remove(os.path.join(hooks_dir, hook_file))
                    removed += 1
        if removed:
            print(f"  Removed {removed} stale hook file(s)")
        else:
            print("  None found")
    else:
        print("  No hooks directory")

    print("\nDone.")


def _api_get(path: str):
    import json
    import urllib.request
    token = _read_token()
    req = urllib.request.Request(f"http://127.0.0.1:9100{path}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read())


def _api_post(path: str, body: dict | None = None):
    import json
    import urllib.request
    token = _read_token()
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(
        f"http://127.0.0.1:9100{path}",
        data=data or b"",
        headers=headers,
        method="POST",
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read())


def _nodes_cmd(subargs: list[str]):
    watch = "--watch" in subargs
    if not watch:
        _print_nodes()
    else:
        _watch_nodes()


def _print_nodes():
    try:
        tree = _api_get("/api/tree")
    except Exception as e:
        print(f"Failed to reach Armada server: {e}", file=sys.stderr)
        sys.exit(1)

    def _collect(nodes, depth=0):
        rows = []
        for n in nodes:
            icon = {"active": "\033[32m●\033[0m",
                    "pending": "\033[33m●\033[0m",
                    "error": "\033[31m●\033[0m",
                    "dead": "\033[2m●\033[0m",
                    "idle": "\033[0m○\033[0m"}.get(n["status"], "○")
            rows.append({
                "id": n["id"],
                "name": n["name"],
                "icon": icon,
                "status": n["status"],
                "project": n.get("project_label_name", "") or "",
                "message": n.get("latest_message", "") or "",
                "depth": depth,
            })
            if n.get("children"):
                rows.extend(_collect(n["children"], depth + 1))
        return rows

    rows = _collect(tree)
    if not rows:
        print("No agents. Create one with the dashboard or API.")
        return

    for r in rows:
        indent = "  " * r["depth"]
        print(f"  {r['icon']} {indent}\033[1m{r['name']}\033[0m  "
              f"\033[2m{r['status']}\033[0m  {r['project']}")
        if r["message"]:
            print(f"     {indent}\033[2m{r['message'][:80]}\033[0m")


def _strip_ansi(s):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)


def _get_attached():
    """Return set of node names that currently have a tmux client attached."""
    import subprocess
    try:
        r = subprocess.run(["tmux", "list-clients", "-F", "#{client_session}"],
                          capture_output=True, text=True, timeout=2)
        return {s.replace("armada-", "") for s in r.stdout.strip().split("\n") if s}
    except Exception:
        return set()


def _focus_iterm():
    """Bring iTerm to the foreground."""
    import subprocess
    try:
        subprocess.run(["osascript", "-e",
            'tell application "iTerm" to activate'], capture_output=True)
    except Exception:
        pass


def _focus_attached_node(name):
    """Focus the iTerm tab/window already attached to the given node name."""
    import subprocess
    system = platform.system()
    if system != "Darwin":
        _focus_iterm()
        return

    script = f'''
    tell application "iTerm"
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if name of s contains "{name}" then
                        select w
                        select t
                        select s
                        activate
                        return "found"
                    end if
                end repeat
            end repeat
        end repeat
        activate
        return "notfound"
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
    except Exception:
        _focus_iterm()


def _watch_nodes():
    import select
    import tty
    import termios

    if not os.environ.get("TMUX"):
        import shutil
        armada = shutil.which("armada") or sys.argv[0]
        result = subprocess.run(["tmux", "has-session", "-t", "armada_watch"],
                               capture_output=True)
        if result.returncode == 0:
            os.execvp("tmux", ["tmux", "attach-session", "-d", "-t", "armada_watch"])
        os.execvp("tmux", ["tmux", "new-session", "-s", "armada_watch", armada, "watch"])

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    rows = []
    projects = []
    selected = 0
    view = "nodes"
    _seen_pending = set()
    _status_msg = ""

    subprocess.run(["tmux", "rename-window", "⚓ CLI"], capture_output=True)
    subprocess.run(["tmux", "set-option", "allow-rename", "off"], capture_output=True)
    subprocess.run(["tmux", "set-option", "automatic-rename", "off"], capture_output=True)
    subprocess.run(["tmux", "set-option", "set-titles", "on"], capture_output=True)
    subprocess.run(["tmux", "set-option", "set-titles-string", "⛵ WATCH ⛵"], capture_output=True)

    try:
        tty.setcbreak(fd)

        while True:
            tw = os.get_terminal_size().columns

            try:
                tree = _api_get("/api/tree")
            except Exception:
                tree = None
            try:
                projects = _api_get("/api/project-labels")
            except Exception:
                pass

            # Detect new pending nodes for alert
            rows_check = _watch_collect_nodes(tree) if tree else []
            current_pending = {r["id"] for r in rows_check if r["status"] == "pending"}
            new_pending = current_pending - _seen_pending
            _seen_pending = current_pending
            has_pending = bool(current_pending)
            if new_pending:
                sys.stdout.write("\a")
                sys.stdout.flush()

            attached = _get_attached()

            if view == "nodes":
                _watch_draw_nodes(tree, projects, selected, tw, has_pending, attached, _status_msg)
            else:
                pending_names = [r["name"] for r in rows_check if r["status"] == "pending"]
                _watch_draw_projects(projects, selected, tw, has_pending, pending_names)

            sys.stdout.flush()

            ch = None
            if select.select([sys.stdin], [], [], 1.5)[0]:
                b = os.read(fd, 1)
                if b == b'\x1b':
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        b += os.read(fd, 2)
                data = b.decode('utf-8', errors='replace')
                if data == '\x1b[A':
                    ch = 'UP'
                elif data == '\x1b[B':
                    ch = 'DOWN'
                elif data == '\x1b[C':
                    ch = 'RIGHT'
                elif data == '\x1b[D':
                    ch = 'LEFT'
                else:
                    ch = data

            if ch == 'q':
                break

            elif ch == '\t':
                view = "projects" if view == "nodes" else "nodes"
                selected = 0
                _status_msg = ""

            elif view == "nodes":
                rows = _watch_collect_nodes(tree)
                if selected >= len(rows):
                    selected = max(0, len(rows) - 1)

                if ch == 'UP':
                    selected = max(0, selected - 1)
                    _status_msg = ""
                elif ch == 'DOWN':
                    selected = min(len(rows) - 1, selected + 1)
                    _status_msg = ""
                elif (ch == '\r' or ch == '\n') and rows:
                    name = rows[selected]["name"]
                    try:
                        if name in attached:
                            _focus_attached_node(name)
                            _status_msg = f"Focused {name}"
                        else:
                            _api_post(f"/api/nodes/{rows[selected]['id']}/attach")
                            _status_msg = f"Attaching to {name}..."
                    except Exception as e:
                        _status_msg = f"Attach error: {e}"
                elif ch == 'a' and rows:
                    name = rows[selected]["name"]
                    try:
                        ok, msg = _attach_split(name, quiet=True)
                        _status_msg = msg
                    except Exception as e:
                        _status_msg = f"Attach error: {e}"
                elif ch == 'k' and rows:
                    try:
                        import urllib.request as ur
                        tok = _read_token()
                        req = ur.Request(
                            f"http://127.0.0.1:9100/api/nodes/{rows[selected]['id']}",
                            method="DELETE")
                        if tok:
                            req.add_header("Authorization", f"Bearer {tok}")
                        ur.urlopen(req, timeout=5)
                    except Exception:
                        pass
                elif ch == 'd' and rows:
                    try:
                        import json as _json
                        import urllib.request as ur
                        tok = _read_token()
                        body = _json.dumps({"action": "hide"}).encode()
                        req = ur.Request(
                            f"http://127.0.0.1:9100/api/nodes/{rows[selected]['id']}",
                            data=body,
                            headers={"Content-Type": "application/json"},
                            method="PATCH")
                        if tok:
                            req.add_header("Authorization", f"Bearer {tok}")
                        ur.urlopen(req, timeout=5)
                    except Exception:
                        pass
                elif ch == 'n':
                    err = _watch_add_node(fd, old_settings, projects)
                    if err:
                        _status_msg = err
                    tty.setcbreak(fd)

            elif view == "projects":
                if selected >= len(projects):
                    selected = max(0, len(projects) - 1)

                if ch == 'UP':
                    selected = max(0, selected - 1)
                elif ch == 'DOWN':
                    selected = min(len(projects) - 1, selected + 1)
                elif ch == 'n' and projects:
                    _watch_add_project(fd, old_settings)
                    tty.setcbreak(fd)
                elif ch == 'd' and projects:
                    try:
                        import urllib.request as ur
                        tok = _read_token()
                        req = ur.Request(
                            f"http://127.0.0.1:9100/api/project-labels/{projects[selected]['id']}",
                            method="DELETE")
                        if tok:
                            req.add_header("Authorization", f"Bearer {tok}")
                        ur.urlopen(req, timeout=5)
                    except Exception:
                        pass
                    selected = max(0, selected - 1)

    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[H\033[J")
        sys.stdout.flush()
        print("Stopped.")


def _watch_collect_nodes(tree):
    rows = []
    if not tree:
        return rows
    def _collect(nodes, depth=0):
        for n in nodes:
            rows.append({
                "id": n["id"], "name": n["name"],
                "status": n["status"],
                "colour": n.get("colour", "#8b949e"),
                "project": n.get("project_label_name", "") or "",
                "message": n.get("latest_message", "") or "",
                "depth": depth,
            })
            if n.get("children"):
                _collect(n["children"], depth + 1)
    _collect(tree)
    return rows


def _watch_draw_nodes(tree, projects, selected, tw, has_pending=False, attached=None, status_msg=""):
    rows = _watch_collect_nodes(tree)
    pending_ids = {r["id"] for r in rows if r["status"] == "pending"}
    pending_names = [r["name"] for r in rows if r["id"] in pending_ids]
    active = sum(1 for r in rows if r["status"] == "active")
    pending = sum(1 for r in rows if r["status"] == "pending")
    idle = sum(1 for r in rows if r["status"] == "idle")
    if attached is None:
        attached = set()

    sys.stdout.write("\033[H\033[J")

    top = f" \033[7m Nodes \033[0m  Projects   |  " \
          f"\033[32m{active} active\033[0m  " \
          f"\033[33m{pending} pending\033[0m  " \
          f"\033[2m{idle} idle\033[0m  |  {len(rows)} agents"
    sys.stdout.write(f"\033[1m{top}\033[0m\n\n")

    if not rows:
        sys.stdout.write("  No agents.\n")
    else:
        for i, r in enumerate(rows):
            icon = "●" if r["status"] in ("active", "pending", "error") else "○"
            is_dead = r["status"] == "dead"
            icon_color = {"active": "\033[32m", "pending": "\033[33m\033[5m",
                     "error": "\033[31m", "dead": "\033[2m",
                     "idle": ""}.get(r["status"], "")
            if is_dead:
                icon_color = "\033[2m"
            name_color = "\033[2m" if is_dead else _hex_to_ansi(r.get("colour", "#8b949e"))
            at = "\033[32m▣\033[0m" if r["name"] in attached else " "
            indent = "  " * r["depth"]
            line = f" {icon_color}{icon} {indent}{name_color}{r['name'][:30]:<30}\033[0m" \
                   f" \033[2m{r['status']:<7}\033[0m{at} {r['project'][:18]:<18} {r['message'][:50]}"
            line = line.ljust(tw)
            if i == selected:
                sys.stdout.write(f"\033[7m{_strip_ansi(line)}\033[0m\n")
            else:
                sys.stdout.write(f"{line}\n")

    if pending:
        sys.stdout.write(f"\n\033[33m⚠ Pending: {', '.join(pending_names)}\033[0m\n")

    if status_msg:
        is_error = status_msg.startswith("Failed") or status_msg.startswith("No tmux") or status_msg.startswith("Not inside") or status_msg.startswith("Node not")
        color = "\033[31m" if is_error else "\033[32m"
        sys.stdout.write(f"\n{color}  {status_msg}\033[0m\n")

    _watch_draw_bottom(tw, "[↑↓]nav [enter]attach [n]ew [k]kill [d]delete [tab]projects [q]quit")


def _watch_draw_projects(projects, selected, tw, has_pending=False, pending_names=None):
    sys.stdout.write("\033[H\033[J")

    nodes_tab = "\033[33m⚠ Nodes \033[0m" if has_pending else " Nodes "
    top = f" {nodes_tab} \033[7m Projects \033[0m   |  {len(projects)} projects"
    sys.stdout.write(f"\033[1m{top}\033[0m\n\n")

    if not projects:
        sys.stdout.write("  No projects. Press [n] to add one.\n")
    else:
        for i, p in enumerate(projects):
            line = f"   {p['name'][:25]:<25} {p['id'][:20]:<20} {p['path'][:50]}"
            line = line.ljust(tw)
            if i == selected:
                sys.stdout.write(f"\033[7m{_strip_ansi(line)}\033[0m\n")
            else:
                sys.stdout.write(f"{line}\n")

    if has_pending and pending_names:
        sys.stdout.write(f"\n\033[33m⚠ Pending: {', '.join(pending_names)}\033[0m\n")

    _watch_draw_bottom(tw, "[↑↓]nav [n]ew [d]elete [tab]nodes [q]quit")


def _watch_draw_bottom(tw, shortcuts):
    sys.stdout.write(f"\n\033[7m {shortcuts} \033[0m")


def _hex_to_ansi(hex_colour: str) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    _MAP = [
        (0xEF, 0x44, 0x44, "31"),     # red
        (0xF9, 0x73, 0x16, "1;33"),   # orange → bright yellow
        (0xEA, 0xB3, 0x08, "33"),     # yellow
        (0x22, 0xC5, 0x5E, "32"),     # green
        (0x14, 0xB8, 0xA6, "1;36"),   # teal → bright cyan
        (0x3B, 0x82, 0xF6, "34"),     # blue
        (0x63, 0x66, 0xF1, "1;34"),   # indigo → bright blue
        (0xA8, 0x55, 0xF7, "35"),     # purple
        (0xEC, 0x48, 0x99, "1;35"),   # pink → bright magenta
        (0x06, 0xB6, 0xD4, "36"),     # cyan
        (0x84, 0xCC, 0x16, "1;32"),   # lime → bright green
        (0xD9, 0x46, 0xEF, "1;31"),   # fuchsia → bright red
    ]
    best = min(_MAP, key=lambda m: abs(m[0] - r) + abs(m[1] - g) + abs(m[2] - b))
    return f"\033[{best[3]}m"


def _watch_form(fd, old_settings, title, fields):
    """Show an interactive form. fields = [{"label": str, "value": str, "type": "text"|"select", "options": [...]}, ...]
    Last item should be a save button: {"label": "[ Save ]", "type": "button"}
    Returns dict of field values on Save, None on Cancel."""
    import termios
    import tty
    import select

    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    tty.setcbreak(fd)

    active = 0
    try:
        while True:
            sys.stdout.write("\033[H\033[J")
            tw = os.get_terminal_size().columns
            sys.stdout.write(f"\033[1m{title}\033[0m\n\n")

            for i, f in enumerate(fields):
                if f.get("type") == "button":
                    prefix = "\033[7m \033[32m" if i == active else " \033[2m"
                    suffix = "\033[0m"
                    sys.stdout.write(f"{prefix}{f['label']}{suffix}\n")
                    continue

                prefix = "\033[7m" if i == active else ""
                suffix = "\033[0m" if i == active else ""
                req = "" if not f.get("required") else " *"
                label = f["label"] + req

                if f.get("type") == "select" and f.get("options"):
                    opts = f["options"]
                    idx = opts.index(f["value"]) if f["value"] in opts else 0
                    val = f" \033[2m◀\033[0m {opts[idx]} \033[2m▶\033[0m "
                else:
                    val = f["value"] + "\033[7m \033[0m" if i == active else f["value"]

                line = f" {prefix} {label:<20} {val}{suffix} "
                sys.stdout.write(line.ljust(tw)[:tw] + "\n")

            sys.stdout.write("\n\033[2m[tab/↑↓]field  [←→]change  [esc]cancel\033[0m")
            sys.stdout.flush()

            b = os.read(fd, 1)
            if b == b'\x1b':
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    seq = os.read(fd, 2)
                    if seq == b'[A':
                        active = max(0, active - 1)
                    elif seq == b'[B':
                        active = min(len(fields) - 1, active + 1)
                    elif seq == b'[C' and fields[active].get("type") == "select":
                        opts = fields[active].get("options", [])
                        if opts:
                            cur = fields[active]["value"]
                            idx = (opts.index(cur) + 1) % len(opts) if cur in opts else 0
                            fields[active]["value"] = opts[idx]
                    elif seq == b'[D' and fields[active].get("type") == "select":
                        opts = fields[active].get("options", [])
                        if opts:
                            cur = fields[active]["value"]
                            idx = (opts.index(cur) - 1) % len(opts) if cur in opts else 0
                            fields[active]["value"] = opts[idx]
                    else:
                        return None
                else:
                    return None
            elif b == b'\t':
                active = (active + 1) % len(fields)
            elif b == b'\r' or b == b'\n':
                if fields[active].get("type") == "button":
                    break
            elif b == b'\x7f' and fields[active].get("type") != "select":
                fields[active]["value"] = fields[active]["value"][:-1]
            elif b == b' ' or (b[0] >= 32 and b[0] < 127):
                if fields[active].get("type") != "select":
                    fields[active]["value"] += b.decode()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return {f["label"]: f["value"].strip() for f in fields if f.get("type") != "button"}


def _watch_add_node(fd, old_settings, projects):
    proj_opts = [p["id"] for p in projects] if projects else [""]
    fields = [
        {"label": "Name", "value": "", "type": "text"},
        {"label": "Project", "value": proj_opts[0] if proj_opts else "", "type": "select", "options": proj_opts, "required": True},
        {"label": "Agent", "value": "auto", "type": "select", "options": ["auto", "opencode", "claude", "bash"]},
        {"label": "Parent ID", "value": "", "type": "text"},
        {"label": "Prompt", "value": "", "type": "text"},
        {"label": "[ Save ]", "type": "button"},
    ]
    result = _watch_form(fd, old_settings, "New Node", fields)
    if not result:
        return None
    try:
        body = {
            "project_label_id": result["Project"],
            "agent_type": result["Agent"] or "auto",
        }
        if result["Name"]:
            body["name"] = result["Name"].replace(".", "-")
        if result["Parent ID"]:
            body["parent_id"] = int(result["Parent ID"])
        if result["Prompt"]:
            body["initial_prompt"] = result["Prompt"]
        _api_post("/api/nodes", body)
    except Exception as e:
        return f"Failed: {e}"
    return None


def _watch_add_project(fd, old_settings):
    fields = [
        {"label": "ID", "value": "", "type": "text", "required": True},
        {"label": "Name", "value": "", "type": "text", "required": True},
        {"label": "Path", "value": "", "type": "text", "required": True},
        {"label": "[ Save ]", "type": "button"},
    ]
    result = _watch_form(fd, old_settings, "New Project", fields)
    if not result or not result["ID"] or not result["Name"] or not result["Path"]:
        return
    try:
        _api_post("/api/project-labels", {"id": result["ID"], "name": result["Name"], "path": result["Path"]})
    except Exception:
        pass


def _notify_desktop(title: str, message: str):
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run([
                "osascript", "-e",
                f'display notification "{message}" with title "{title}"'
            ], capture_output=True, timeout=3)
        elif system == "Linux":
            subprocess.run([
                "notify-send", title, message, "--app-name=Armada"
            ], capture_output=True, timeout=3)
    except Exception:
        pass


def _watch_cmd(subargs: list[str]):
    _watch_nodes()


def _create_cmd(subargs: list[str]):
    import argparse
    p = argparse.ArgumentParser(prog="armada create", description="Create a new agent node")
    p.add_argument("--name", "-n", help="Node name (auto-generated if omitted)")
    p.add_argument("--project", "-p", required=True, help="Project label ID (required)")
    p.add_argument("--agent", "-a", default="auto",
                   choices=["auto", "opencode", "claude", "bash"],
                   help="Agent type (default: auto)")
    p.add_argument("--parent", "-P", type=int, help="Parent node ID")
    p.add_argument("--prompt", "-m", help="Initial prompt to send to the agent")
    try:
        ns = p.parse_args(subargs)
    except SystemExit:
        return

    body = {
        "project_label_id": ns.project,
        "agent_type": ns.agent,
    }
    if ns.name:
        body["name"] = ns.name.replace(".", "-")
    if ns.parent:
        body["parent_id"] = ns.parent
    if ns.prompt:
        body["initial_prompt"] = ns.prompt

    try:
        result = _api_post("/api/nodes", body)
        print(f"Created node {result['name']} (id={result['id']})")
    except Exception as e:
        resp = ""
        try:
            resp = str(e.read(), "utf-8")[:200]
        except Exception:
            pass
        print(f"Failed: {e}\n{resp}", file=sys.stderr)
        sys.exit(1)


def _projects_cmd(subargs: list[str]):
    if subargs and subargs[0] == "add":
        if len(subargs) < 4:
            print("Usage: armada projects add <id> <name> <path>")
            sys.exit(1)
        try:
            _api_post("/api/project-labels", {
                "id": subargs[1], "name": subargs[2], "path": subargs[3],
            })
            print(f"Added project {subargs[1]}")
        except Exception as e:
            print(f"Failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if subargs and subargs[0] == "rm":
        if len(subargs) < 2:
            print("Usage: armada projects rm <id>")
            sys.exit(1)
        try:
            import urllib.request as ur
            token = _read_token()
            req = ur.Request(
                f"http://127.0.0.1:9100/api/project-labels/{subargs[1]}",
                method="DELETE")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            ur.urlopen(req, timeout=5)
            print(f"Removed project {subargs[1]}")
        except Exception as e:
            print(f"Failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    try:
        labels = _api_get("/api/project-labels")
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)

    if not labels:
        print("No projects.")
        return

    print(f"{'ID':<20} {'Name':<20} Path")
    print("-" * 70)
    for lb in labels:
        print(f"{lb['id']:<20} {lb['name']:<20} {lb['path']}")


def _kill_node(search: str):
    try:
        tree = _api_get("/api/tree")
    except Exception as e:
        print(f"Failed to reach server: {e}")
        return

    def _find(nodes):
        for n in nodes:
            if str(n["id"]) == search or n["name"] == search:
                return n
            if n.get("children"):
                r = _find(n["children"])
                if r:
                    return r
        return None

    node = _find(tree)
    if not node:
        print(f"Node not found: {search}")
        return

    try:
        import urllib.request as ur
        token = _read_token()
        req = ur.Request(f"http://127.0.0.1:9100/api/nodes/{node['id']}", method="DELETE")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        ur.urlopen(req, timeout=5)
        print(f"Killed {node['name']}")
    except Exception as e:
        print(f"Failed: {e}")


def _find_node(search: str):
    try:
        tree = _api_get("/api/tree")
    except Exception as e:
        print(f"Failed to reach Armada server: {e}", file=sys.stderr)
        return None

    def _find(nodes):
        for n in nodes:
            if str(n["id"]) == search or n["name"] == search:
                return n
            if n.get("children"):
                r = _find(n["children"])
                if r:
                    return r
        return None

    node = _find(tree)
    if not node:
        print(f"Node not found: {search}", file=sys.stderr)
    return node


def _switch_client(search: str, quiet: bool = False):
    node = _find_node(search)
    if not node:
        msg = f"Node not found: {search}"
        if quiet:
            return False, msg
        print(msg, file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("TMUX"):
        msg = "Not inside a tmux session"
        if quiet:
            return False, msg
        print(msg, file=sys.stderr)
        sys.exit(1)

    name = node["name"]
    session_id = node.get("tmux_session_id")
    session = session_id or f"armada-{name}"

    try:
        result = subprocess.run(["tmux", "has-session", "-t", session],
                                capture_output=True)
        if result.returncode != 0:
            msg = f"No tmux session for {name} (node may not be active)"
            if quiet:
                return False, msg
            print(msg, file=sys.stderr)
            sys.exit(1)
        subprocess.run(["tmux", "switch-client", "-t", session], check=True)
    except subprocess.CalledProcessError as e:
        msg = f"Failed to attach: {e}"
        if quiet:
            return False, msg
        print(msg, file=sys.stderr)
        sys.exit(1)

    msg = f"Switched to {name}"
    if not quiet:
        print(msg)
    return True, msg


def _attach_node(search: str, exit_on_error: bool = True):
    search = search.replace(".", "-")
    node = _find_node(search)
    if not node:
        if exit_on_error:
            sys.exit(1)
        return

    nid = node["id"]
    try:
        _api_post(f"/api/nodes/{nid}/attach")
        print(f"Attached to {node['name']}")
    except Exception as e:
        resp_body = ""
        try:
            resp_body = str(e.read(), "utf-8")[:200]
        except Exception:
            pass
        print(f"Failed to attach: {e}\n{resp_body}", file=sys.stderr)
        if exit_on_error:
            sys.exit(1)


def _attach_split(search: str, quiet: bool = False):
    search = search.replace(".", "-")
    node = _find_node(search)
    if not node:
        msg = f"Node not found: {search}"
        if quiet:
            return False, msg
        print(msg, file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("TMUX"):
        msg = "Not inside a tmux session. Run 'tmux' first, then try again."
        if quiet:
            return False, msg
        print(msg, file=sys.stderr)
        print("  tmux", file=sys.stderr)
        print(f"  armada attach --split {search}", file=sys.stderr)
        sys.exit(1)

    session = f"armada-{node['name']}"
    try:
        result = subprocess.run(["tmux", "has-session", "-t", session], capture_output=True)
        if result.returncode != 0:
            msg = f"No tmux session for {node['name']} (node may not be active)"
            if quiet:
                return False, msg
            print(msg, file=sys.stderr)
            sys.exit(1)

        cmd = f'unset TMUX; tmux attach -d -t "{session}"'

        r1 = subprocess.run(["tmux", "split-window", "-v", cmd],
                           capture_output=True, text=True)
        if r1.returncode != 0:
            msg = f"split-window failed: {r1.stderr.strip()}"
            if quiet:
                return False, msg
            print(msg, file=sys.stderr)
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        msg = f"Failed to split and attach: {e}"
        if quiet:
            return False, msg
        print(msg, file=sys.stderr)
        sys.exit(1)

    msg = f"Attached to {node['name']}"
    if not quiet:
        print(msg)
    return True, msg


def _report_cmd(subargs: list[str]):
    """Report node status: armada report <status> <message> [--options '<json>']"""
    import json
    import urllib.request
    import urllib.error

    node_name = os.environ.get("ARMADA_NODE_NAME", "")
    if not node_name:
        return

    options_json = ""
    filtered = []
    i = 0
    while i < len(subargs):
        if subargs[i] == "--options" and i + 1 < len(subargs):
            options_json = subargs[i + 1]
            i += 2
        else:
            filtered.append(subargs[i])
            i += 1

    if len(filtered) < 1:
        print("Usage: armada report <status> <message> [--options '<json>']", file=sys.stderr)
        sys.exit(1)

    status = filtered[0]
    message = " ".join(filtered[1:]) if len(filtered) > 1 else ""

    api_base = os.environ.get("ARMADA_API", f"http://127.0.0.1:{constants.DEFAULT_PORT}")
    body: dict = {"name": node_name, "status": status, "message": message}
    if options_json:
        try:
            body["options"] = json.loads(options_json)
        except json.JSONDecodeError:
            pass

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{api_base}/api/report",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _demodb_cmd(subargs: list[str]):
    from . import demodb
    force = "--force" in subargs
    if not subargs or subargs[0] == "seed":
        demodb.seed(force=force)
    elif subargs[0] == "path":
        print(constants.DB_PATH)
    else:
        print("Usage: armada demodb [seed|path] [--force]")
        print("  seed     Seed a demo database at ARMADA_DB_PATH (or ~/.armada/armada-demo.db)")
        print("  path     Print the current DB path (respects ARMADA_DB_PATH env var)")
        print()
        print("  Default: ARMADA_DB_PATH=~/.armada/armada-demo.db")
        print("  Safety:  refuses to seed non-demo DBs unless --force is given")
        sys.exit(1)
