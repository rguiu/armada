import os
import sys
import signal
import socket
import subprocess
import platform


def _hyperlink(url: str, text: str | None = None) -> str:
    if text is None:
        text = url
    return f"\033]8;;{url}\007{text}\033]8;;\007"


def _get_pid_from_port(port: int = 9100) -> int | None:
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
    keep_token = "--keep-token" in args or "--no-token-rotate" in args
    args = [a for a in args if a not in ("--lan", "--qr", "--keep-token", "--no-token-rotate")]

    if not args or args[0] in ("start", "serve"):
        from .server import start_server, _ensure_token
        _ensure_token(keep=True)
        _print_startup_info(lan=lan, qr=qr)
        start_server(daemon=True, open_browser=True, lan=lan, keep_token=keep_token)

    elif args[0] == "stop":
        _stop_server()

    elif args[0] == "attach":
        from .server import start_server, _ensure_token
        _ensure_token(keep=True)
        _print_startup_info(lan=lan, qr=qr)
        start_server(daemon=False, open_browser=False, lan=lan)

    elif args[0] == "setup":
        _setup_skills()

    elif args[0] == "token":
        _print_token(qr=qr, lan=lan)

    elif args[0] == "doctor":
        nuke = "--nuke" in args
        _doctor(nuke=nuke)

    elif args[0] == "status":
        _status()

    elif args[0] == "config":
        _config(args[1:])

    else:
        print("Usage: armada [start|stop|attach|setup|token|doctor|status|config] [--lan] [--qr] [--keep-token]")
        print("  start        Start the Armada server daemon + open dashboard")
        print("  stop         Stop the Armada server")
        print("  attach       Start server in foreground (for debugging)")
        print("  setup        Install Armada skills to user profile")
        print("  token        Print the auth token (--qr for scannable QR code)")
        print("  doctor       Clean up orphaned tmux sessions and stale state")
        print("  status       Show server and node status")
        print("  config       Show or manage configuration (~/.armada/config.yaml)")
        print("  --lan        Bind to / use LAN IP (for other devices on network)")
        print("  --qr         Show QR code (with token command)")
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
    token_file = os.path.expanduser("~/.armada/token")
    try:
        token = open(token_file).read().strip()
    except FileNotFoundError:
        return

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
    token_file = os.path.expanduser("~/.armada/token")
    try:
        token = open(token_file).read().strip()
    except FileNotFoundError:
        print("No token found. Start Armada first with: armada start", file=sys.stderr)
        sys.exit(1)

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


def _setup_skills():
    from . import tmux
    paths = tmux.install_user_skills()
    if not paths:
        print("Could not detect Open Code or Claude Code. Skills not installed.")
        print("Create .opencode/skills/ or .claude/skills/ in your home directory first.")
        sys.exit(1)
    for p in paths:
        print(f"Installed: {p}")
    print(f"\nSkills installed to {len(paths)} location(s). Agents will now auto-load Armada skills.")


def _status():
    import sqlite3
    from . import tmux as _tmux_mod

    pid_file = os.path.expanduser("~/.armada/server.pid")
    server_running = False
    server_pid = None
    if os.path.exists(pid_file):
        try:
            server_pid = int(open(pid_file).read().strip())
            os.kill(server_pid, 0)
            server_running = True
        except (ValueError, ProcessLookupError, IOError):
            pass

    if not server_running:
        found_pid = _get_pid_from_port(9100)
        if found_pid:
            server_pid = found_pid
            server_running = True

    if server_running:
        print(f"Server: running (PID {server_pid})")
    else:
        print("Server: stopped")

    if _tmux_mod._has_tmux():
        windows = _tmux_mod.running_window_names()
        print(f"Tmux:   armada session with {len(windows)} window(s)")
    else:
        print("Tmux:   not installed")
        return

    db_path = os.path.expanduser("~/.armada/armada.db")
    if not os.path.exists(db_path):
        print("DB:     not found")
        return

    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    nodes = conn.execute(
        "SELECT n.name, n.status, n.colour, n.agent_type, n.created_at, "
        "  (SELECT message FROM status_reports WHERE node_id = n.id "
        "   ORDER BY timestamp DESC LIMIT 1) as message "
        "FROM nodes n WHERE n.killed_at IS NULL AND n.hidden_at IS NULL "
        "ORDER BY n.created_at DESC"
    ).fetchall()
    conn.close()

    if not nodes:
        print("Nodes:  none active")
        return

    print(f"Nodes:  {len(nodes)} active\n")
    for n in nodes:
        status_icon = {"active": "+", "idle": "-", "pending": "?", "error": "!"}.get(n["status"], " ")
        msg = n["message"] or ""
        if len(msg) > 50:
            msg = msg[:47] + "..."
        print(f"  [{status_icon}] {n['name']:<20} {n['status']:<8} {n['agent_type']:<10} {msg}")


def _doctor(nuke: bool = False):
    import glob
    from . import tmux as _tmux_mod

    print("Armada Doctor")
    print("=" * 40)

    if nuke:
        print("\n[NUKE] Killing ALL armada tmux sessions and resetting DB...")
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            killed = 0
            for session in result.stdout.strip().split("\n"):
                if session.startswith("armada") or session.startswith("_view_"):
                    subprocess.run(["tmux", "kill-session", "-t", session],
                                   capture_output=True)
                    killed += 1
            print(f"  Killed {killed} tmux session(s)")

        db_path = os.path.expanduser("~/.armada/armada.db")
        if os.path.exists(db_path):
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM status_reports")
            conn.execute("DELETE FROM nodes")
            conn.commit()
            conn.close()
            print("  Reset DB (cleared nodes and reports)")

        temps = glob.glob("/tmp/_armada_*")
        for f in temps:
            try:
                os.remove(f)
            except OSError:
                pass
        if temps:
            print(f"  Removed {len(temps)} temp file(s)")

        print("\nDone. Fresh start.")
        return

    # 0. Kill stale armada server processes
    print("\n[0] Stale server processes")
    current_server_pid = None
    pid_file = os.path.expanduser("~/.armada/server.pid")
    if os.path.exists(pid_file):
        try:
            current_server_pid = int(open(pid_file).read().strip())
        except (ValueError, IOError):
            pass

    stale_killed = 0
    db_path = os.path.expanduser("~/.armada/armada.db")
    if os.path.exists(db_path):
        pids = _get_db_lock_pids(db_path, current_server_pid)
        for pid in pids:
            try:
                cmdline = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "command="],
                    capture_output=True, text=True,
                ).stdout.strip()
                if "armada" in cmdline and "python" in cmdline.lower():
                    os.kill(pid, signal.SIGTERM)
                    stale_killed += 1
            except (ProcessLookupError, PermissionError):
                pass

    if stale_killed:
        print(f"  Killed {stale_killed} stale server process(es)")
    else:
        print("  None found")

    if os.path.exists(db_path):
        try:
            import sqlite3
            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception:
            pass

    # 1. Kill orphaned _view_* sessions
    print("\n[1] Orphaned _view_* sessions")
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        sessions = result.stdout.strip().split("\n")
        view_sessions = [s for s in sessions if s.startswith("_view_")]
        if view_sessions:
            for session in view_sessions:
                subprocess.run(["tmux", "kill-session", "-t", session],
                               capture_output=True)
            print(f"  Killed {len(view_sessions)} orphaned view session(s)")
        else:
            print("  None found")
    else:
        print("  tmux not running")

    # 2. Kill duplicate armada-N grouped sessions
    print("\n[2] Duplicate armada-N sessions")
    if result.returncode == 0:
        dupes = [s for s in sessions if s.startswith("armada-") and s[7:].isdigit()]
        if dupes:
            for session in dupes:
                subprocess.run(["tmux", "kill-session", "-t", session],
                               capture_output=True)
            print(f"  Killed {len(dupes)} duplicate session(s)")
        else:
            print("  None found")

    # 3. Sync DB — mark nodes dead if their tmux window is gone
    print("\n[3] Stale DB nodes (tmux window gone)")
    if os.path.exists(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        live_nodes = conn.execute(
            "SELECT id, name FROM nodes WHERE killed_at IS NULL AND hidden_at IS NULL"
        ).fetchall()

        running = _tmux_mod.running_window_names()
        stale = [(r["id"], r["name"]) for r in live_nodes if r["name"] not in running]

        if stale:
            for node_id, name in stale:
                conn.execute(
                    "UPDATE nodes SET killed_at = datetime('now'), status = 'dead' WHERE id = ?",
                    (node_id,),
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

    found_pid = _get_pid_from_port(9100)
    if found_pid:
        try:
            os.kill(found_pid, signal.SIGTERM)
            print(f"Stopped Armada server (PID {found_pid}, found via port).")
        except ProcessLookupError:
            pass


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
    import glob

    skill_dir = os.path.join(os.path.dirname(__file__), "..", "skills")
    if not os.path.isdir(skill_dir):
        print("Skills directory not found. Run from the armada repo root.", file=sys.stderr)
        sys.exit(1)

    skill_dir = os.path.abspath(skill_dir)
    print(f"Installing skills from {skill_dir}...")

    from .server import TOKEN_FILE
    try:
        token = open(TOKEN_FILE).read().strip()
    except FileNotFoundError:
        token = ""

    if token:
        os.environ["ARMADA_AUTH_TOKEN"] = token
        print(f"  ARMADA_AUTH_TOKEN set")

    installed = tmux.install_skills(skill_dir)
    print(f"  {installed} file(s) installed")

    claude_hooks = os.path.expanduser("~/.claude/hooks")
    if os.path.isdir(claude_hooks):
        tmux._deploy_claude_hooks(skill_dir)
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
    found_pid = _get_pid_from_port(9100)
    pid_file = os.path.expanduser("~/.armada/server.pid")
    pid_file_pid = None
    try:
        with open(pid_file) as f:
            pid_file_pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        pass

    if found_pid:
        print(f"  Listening on port 9100 (PID {found_pid})")
    elif pid_file_pid:
        try:
            os.kill(pid_file_pid, 0)
            print(f"  PID file says {pid_file_pid} (but not on port 9100)")
        except OSError:
            print(f"  PID file says {pid_file_pid} (process is dead — cleaning up)")
            os.remove(pid_file)
    else:
        print("  Not running")

    if nuke:
        print("\n--nuke: Killing all armada tmux sessions and resetting state...")
        try:
            subprocess.run(["tmux", "kill-server"], capture_output=True, timeout=5)
        except Exception:
            pass
        db_path = os.path.expanduser("~/.armada/armada.db")
        if os.path.exists(db_path):
            os.remove(db_path)
            print("  Removed armada.db")
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
    db_path = os.path.expanduser("~/.armada/armada.db")
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
