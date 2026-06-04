import os
import sys
import signal
import socket
import subprocess


def _hyperlink(url: str, text: str | None = None) -> str:
    """Wrap a URL in OSC 8 escape sequence so modern terminals render it clickable."""
    if text is None:
        text = url
    return f"\033]8;;{url}\007{text}\033]8;;\007"


def main():
    args = sys.argv[1:]
    lan = "--lan" in args
    qr = "--qr" in args
    args = [a for a in args if a not in ("--lan", "--qr")]

    if not args or args[0] in ("start", "serve"):
        from .server import start_server, _ensure_token
        _ensure_token()
        _print_startup_info(lan=lan, qr=qr)
        start_server(daemon=True, open_browser=True, lan=lan)

    elif args[0] == "stop":
        _stop_server()

    elif args[0] == "attach":
        from .server import start_server, _ensure_token
        _ensure_token()
        _print_startup_info(lan=lan, qr=qr)
        start_server(daemon=False, open_browser=False, lan=lan)

    elif args[0] == "setup":
        _setup_skills()

    elif args[0] == "token":
        _print_token(qr=qr, lan=lan)

    elif args[0] == "doctor":
        nuke = "--nuke" in args
        _doctor(nuke=nuke)

    else:
        print("Usage: armada [start|stop|attach|setup|token|doctor] [--lan] [--qr]")
        print("  start   Start the Armada server daemon + open dashboard")
        print("  stop    Stop the Armada server")
        print("  attach  Start server in foreground (for debugging)")
        print("  setup   Install Armada skills to user profile")
        print("  token   Print the auth token (--qr for scannable QR code)")
        print("  doctor  Clean up orphaned tmux sessions and stale state")
        print("  --lan   Bind to / use LAN IP (for other devices on network)")
        print("  --qr    Show QR code (with token command)")
        print("  --nuke  (with doctor) Kill ALL armada tmux sessions and reset DB")
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
    token = open(token_file).read().strip()

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


def _doctor(nuke: bool = False):
    import glob
    from . import tmux as _tmux_mod

    print("Armada Doctor")
    print("=" * 40)

    if nuke:
        print("\n[NUKE] Killing ALL armada tmux sessions and resetting DB...")
        # Kill all armada-related sessions
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

        # Reset the DB (delete nodes and reports, keep project labels)
        db_path = os.path.expanduser("~/.armada/armada.db")
        if os.path.exists(db_path):
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM status_reports")
            conn.execute("DELETE FROM nodes")
            conn.commit()
            conn.close()
            print("  Reset DB (cleared nodes and reports)")

        # Clean temp files
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

    # --- Normal doctor (non-destructive cleanup) ---

    # 0. Kill stale armada server processes (DB lock fix)
    print("\n[0] Stale server processes")
    current_server_pid = None
    pid_file = os.path.expanduser("~/.armada/server.pid")
    if os.path.exists(pid_file):
        try:
            current_server_pid = int(open(pid_file).read().strip())
        except (ValueError, IOError):
            pass

    stale_killed = 0
    try:
        fuser = subprocess.run(
            ["fuser", os.path.expanduser("~/.armada/armada.db")],
            capture_output=True, text=True,
        )
        if fuser.returncode == 0:
            pids = [int(p) for p in fuser.stdout.split() if p.strip().isdigit()]
            for pid in pids:
                if pid == current_server_pid or pid == os.getpid():
                    continue
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
    except Exception:
        pass

    if stale_killed:
        print(f"  Killed {stale_killed} stale server process(es)")
    else:
        print("  None found")

    # Checkpoint WAL to release any lock residue
    db_path = os.path.expanduser("~/.armada/armada.db")
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

    # 2. Kill duplicate armada-N grouped sessions (keep the original 'armada')
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
    db_path = os.path.expanduser("~/.armada/armada.db")
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

    # 5. Clean up stale hooks in ~/.armada/hooks/
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

    # No PID file — try to kill by port
    try:
        result = subprocess.run(["lsof", "-ti", ":9100"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split("\n")[0])
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped Armada server (PID {pid}, found via port).")
            return
    except Exception:
        pass

    print("Armada server is not running (no PID file and no process on port 9100).")
