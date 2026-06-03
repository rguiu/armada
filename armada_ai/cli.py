import os
import sys
import signal
import socket
import subprocess


def _hyperlink(url: str, text: str | None = None) -> str:
    """Wrap a URL in OSC 8 escape sequence so modern terminals render it clickable."""
    if text is None:
        text = url
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


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

    else:
        print("Usage: armada [start|stop|attach|setup|token] [--lan] [--qr]")
        print("  start   Start the Armada server daemon + open dashboard")
        print("  stop    Stop the Armada server")
        print("  attach  Start server in foreground (for debugging)")
        print("  setup   Install Armada skills to user profile")
        print("  token   Print the auth token (--qr for scannable QR code)")
        print("  --lan   Bind to / use LAN IP (for other devices on network)")
        print("  --qr    Show QR code (with token command)")
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
