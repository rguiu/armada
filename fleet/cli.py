import os
import sys
import signal


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("start", "serve"):
        from .server import start_server
        start_server(daemon=True, open_browser=True)

    elif args[0] == "stop":
        _stop_server()

    elif args[0] == "attach":
        from .server import start_server
        start_server(daemon=False, open_browser=False)

    else:
        print("Usage: fleet [start|stop|attach]")
        print("  start   Start the Fleet server daemon + open dashboard")
        print("  stop    Stop the Fleet server")
        print("  attach  Start server in foreground (for debugging)")
        sys.exit(1)


def _stop_server():
    pid_file = os.path.expanduser("~/.fleet/server.pid")
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Fleet server (PID {pid}).")
    except FileNotFoundError:
        print("Fleet server is not running (no PID file).")
    except ProcessLookupError:
        print("Fleet server is not running (stale PID file).")
        try:
            os.remove(pid_file)
        except OSError:
            pass
