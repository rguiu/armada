import os
import sys
import signal
import socket
import subprocess


def main():
    args = sys.argv[1:]
    lan = "--lan" in args
    args = [a for a in args if a != "--lan"]

    if not args or args[0] in ("start", "serve"):
        from .server import start_server
        if lan:
            print(f"  LAN mode — dashboard at http://{_lan_ip()}:9100")
        start_server(daemon=True, open_browser=True, lan=lan)

    elif args[0] == "stop":
        _stop_server()

    elif args[0] == "attach":
        from .server import start_server
        if lan:
            print(f"  LAN mode — dashboard at http://{_lan_ip()}:9100")
        start_server(daemon=False, open_browser=False, lan=lan)

    elif args[0] == "setup":
        _setup_skills()

    elif args[0] == "token":
        _print_token()

    else:
        print("Usage: armada [start|stop|attach|setup|token] [--lan]")
        print("  start   Start the Armada server daemon + open dashboard")
        print("  stop    Stop the Armada server")
        print("  attach  Start server in foreground (for debugging)")
        print("  setup   Install Armada skills to user profile")
        print("  token   Print the auth token for API/CLI access")
        print("  --lan   Bind to 0.0.0.0:9100 (accessible from other devices on LAN)")
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


def _print_token():
    token_file = os.path.expanduser("~/.armada/token")
    try:
        token = open(token_file).read().strip()
        if token:
            print(token)
        else:
            print("No token found. Start Armada first with: armada start", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("No token found. Start Armada first with: armada start", file=sys.stderr)
        sys.exit(1)


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
