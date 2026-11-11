import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys

from . import constants

# --- Output styling -------------------------------------------------------

_COLOR_MODE = "auto"  # auto | always | never
_RESET = "\033[0m"
_STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
}
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _color_enabled(stream=None) -> bool:
    if _COLOR_MODE == "always":
        return True
    if _COLOR_MODE == "never":
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    force = os.environ.get("FORCE_COLOR")
    if force is not None:
        return force.strip().lower() not in ("", "0", "false", "no")
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def _style(text: str, *styles: str, stream=None) -> str:
    if not text or not _color_enabled(stream):
        return text
    prefix = "".join(_STYLES[s] for s in styles)
    return f"{prefix}{text}{_RESET}"


def _visible_len(text) -> int:
    return len(_ANSI_RE.sub("", str(text)))


def _header(title: str, subtitle: str = ""):
    line = f"{_style('⚓', 'bold', 'cyan')} {_style(title, 'bold')}"
    if subtitle:
        line += f"  {_style(subtitle, 'dim')}"
    print(line)


def _section(title: str):
    print(_style(f"▸ {title}", "bold", "cyan"))


def _ok(message: str):
    print(f"  {_style('✓', 'green')} {message}")


def _warn(message: str):
    print(f"  {_style('!', 'yellow')} {message}")


def _err(message: str):
    print(f"{_style('✗', 'red', stream=sys.stderr)} {message}", file=sys.stderr)


def _info(message: str):
    print(f"  {_style('•', 'cyan')} {message}")


def _table(headers, rows, aligns=None):
    headers = [str(h) for h in headers]
    rows = [[str(c) for c in row] for row in rows]
    aligns = aligns or ["left"] * len(headers)
    widths = []
    for i, header in enumerate(headers):
        widths.append(max([_visible_len(header)] + [_visible_len(r[i]) for r in rows]))

    def cell(value, index):
        value = str(value)
        padding = " " * max(0, widths[index] - _visible_len(value))
        return padding + value if aligns[index] == "right" else value + padding

    print(("  " + "  ".join(_style(cell(h, i), "bold")
                            for i, h in enumerate(headers))).rstrip())
    print(("  " + "  ".join(_style("─" * w, "dim") for w in widths)).rstrip())
    for row in rows:
        print("  " + "  ".join(cell(c, i) for i, c in enumerate(row)).rstrip())


def _status_marker(status: str) -> tuple[str, str]:
    return {
        "active": ("●", "green"),
        "pending": ("●", "yellow"),
        "idle": ("○", "dim"),
        "error": ("●", "red"),
        "dead": ("●", "dim"),
    }.get(status, ("○", "dim"))


def _status_cell(status: str) -> str:
    marker, colour = _status_marker(status)
    text = f"{marker} {status}"
    return _style(text, colour, "bold" if status in ("active", "pending", "error") else "dim")


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _short_path(path: str) -> str:
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


class _ArmadaHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Color section headings when the terminal supports it."""

    def start_section(self, heading):
        super().start_section(_style(heading, "bold", "cyan"))


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
            result = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True,
            )
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


class _ArmadaParser(argparse.ArgumentParser):
    """ArgumentParser with friendly, stable error behaviour."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(
            1,
            f"{self.prog}: {_style('error:', 'red', stream=sys.stderr)} {message}\n",
        )


# Boolean flags that may appear anywhere on the command line. They are pulled
# out before argparse runs so both `armada --lan` and `armada start --lan` work.
_GLOBAL_FLAGS = {
    "--lan": "lan",
    "--qr": "qr",
    "--no-browser": "no_browser",
    "--keep-token": "keep_token",
    "--no-token-rotate": "keep_token",
    "--foreground": "foreground",
    "--color": "color",
    "--no-color": "no_color",
    "--version": "version",
    "-V": "version",
}

_GLOBAL_DEFAULTS = {
    "lan": False,
    "qr": False,
    "no_browser": False,
    "keep_token": False,
    "foreground": False,
    "color": False,
    "no_color": False,
}


def _extract_global_flags(argv: list[str]) -> tuple[dict, list[str]]:
    opts = dict(_GLOBAL_DEFAULTS)
    opts["version"] = False
    rest: list[str] = []
    for arg in argv:
        name = _GLOBAL_FLAGS.get(arg)
        if name:
            opts[name] = True
        else:
            rest.append(arg)
    return opts, rest


def _print_tmux_error():
    _err("tmux is not installed.")
    print(f"  {_style('Install it with:', 'dim')}", file=sys.stderr)
    print("    macOS:  brew install tmux", file=sys.stderr)
    print("    Ubuntu: sudo apt install tmux", file=sys.stderr)
    print("    Fedora: sudo dnf install tmux", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArmadaParser(
        prog="armada",
        description=(
            f"{_style('⚓ Armada', 'bold', 'cyan')}  "
            f"{_style('persistent tmux sessions for coding agents', 'dim')}\n"
            "Start, supervise, and orchestrate agent sessions from the terminal or dashboard."
        ),
        epilog=(
            f"{_style('examples', 'bold', 'cyan')}\n"
            "  armada                     start the server and open the dashboard\n"
            "  armada --lan --no-browser  expose the dashboard on the LAN\n"
            "  armada nodes --watch       live terminal dashboard\n"
            "  armada agents              show installed agent CLIs\n"
            "  armada create -p armada -a claude -m \"review the auth module\"\n"
            "\n"
            f"{_style('colour', 'bold', 'cyan')}\n"
            "  Colour is automatic on a TTY. Use --color to force it or --no-color\n"
            "  (or NO_COLOR=1) to disable it."
        ),
        formatter_class=_ArmadaHelpFormatter,
        allow_abbrev=False,
    )
    parser.set_defaults(**_GLOBAL_DEFAULTS)

    glob = parser.add_argument_group("global options")
    glob.add_argument("--lan", action="store_true",
                      help="bind to the LAN address (0.0.0.0) instead of localhost")
    glob.add_argument("--no-browser", action="store_true",
                      help="do not open the dashboard in a browser")
    glob.add_argument("--qr", action="store_true",
                      help="print a pairing hint (use 'armada token --qr' once running)")
    glob.add_argument("--keep-token", "--no-token-rotate", dest="keep_token",
                      action="store_true",
                      help="reuse the existing auth token (do not rotate)")
    glob.add_argument("--foreground", action="store_true",
                      help="run the server in the foreground (do not daemonize)")
    glob.add_argument("--color", action="store_true",
                      help="force coloured output")
    glob.add_argument("--no-color", action="store_true",
                      help="disable coloured output")
    glob.add_argument("-V", "--version", action="version",
                      version=f"armada {constants.VERSION}",
                      help="show the Armada version and exit")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND", title="commands")

    p = sub.add_parser("start", aliases=["serve"],
                       help="start the server and open the dashboard")
    p.add_argument("--foreground", action="store_true",
                   help="run in the foreground (do not daemonize)")
    p.add_argument("--lan", action="store_true",
                   help="bind to the LAN address (0.0.0.0)")
    p.add_argument("--no-browser", action="store_true",
                   help="do not open the dashboard in a browser")
    p.add_argument("--qr", action="store_true",
                   help="print a pairing hint (use 'armada token --qr' once running)")
    p.add_argument("--keep-token", "--no-token-rotate", dest="keep_token",
                   action="store_true", help="reuse the existing auth token")
    p.set_defaults(_handler=_cmd_start)

    p = sub.add_parser("stop", help="stop the server")
    p.set_defaults(_handler=_cmd_stop)

    p = sub.add_parser("status", help="show server and fleet status")
    p.add_argument("--json", action="store_true", help="output JSON")
    p.set_defaults(_handler=_cmd_status)

    p = sub.add_parser("nodes", aliases=["list"],
                       help="list agent nodes (or watch them live)")
    p.add_argument("--watch", action="store_true", help="open the live terminal dashboard")
    p.add_argument("--all", action="store_true", help="include dead nodes")
    p.add_argument("--json", action="store_true", help="output JSON")
    p.set_defaults(_handler=_cmd_nodes)

    p = sub.add_parser("watch", help="open the live terminal dashboard (legacy alias)")
    p.set_defaults(_handler=_cmd_watch)

    p = sub.add_parser("create", help="create a new agent node")
    p.add_argument("-p", "--project", metavar="PATH_OR_ID",
                   help="project folder or label ID (default: current directory)")
    p.add_argument("-n", "--name", help="node name (auto-generated if omitted)")
    p.add_argument("-a", "--agent", default="auto",
                   choices=["auto", "opencode", "claude", "bash"],
                   help="agent type (default: auto)")
    p.add_argument("-P", "--parent", type=int, metavar="ID",
                   help="parent node ID")
    p.add_argument("-m", "--prompt", help="initial prompt to send to the agent")
    p.set_defaults(_handler=_cmd_create)

    p = sub.add_parser("attach", help="attach to a node's terminal")
    p.add_argument("name", nargs="?", help="node name (omit for debug server)")
    p.add_argument("--split", action="store_true", help="split the current tmux window")
    p.add_argument("--lan", action="store_true",
                   help="bind the debug server to the LAN address")
    p.add_argument("--qr", action="store_true",
                   help="show a QR code when starting the debug server")
    p.set_defaults(_handler=_cmd_attach)

    p = sub.add_parser("restart", help="kill and recreate a node")
    p.add_argument("target", metavar="NAME_OR_ID", help="node name or numeric ID")
    p.set_defaults(_handler=_cmd_restart)

    p = sub.add_parser("projects", help="manage projects")
    p.set_defaults(_handler=_cmd_projects)
    projects_sub = p.add_subparsers(dest="projects_action", metavar="ACTION")
    projects_sub.add_parser("list", help="list projects (default)")
    projects_sub.add_parser("scan", help="find projects under project_roots")
    pa = projects_sub.add_parser("add", help="register a project folder")
    pa.add_argument("path", help="project directory")
    pa.add_argument("--name", help="display name (default: folder name)")
    pa.add_argument("--id", help="label ID (default: derived from folder name)")
    pr = projects_sub.add_parser("rm", help="remove a project")
    pr.add_argument("id")

    p = sub.add_parser("logs", help="tail a node's activity log")
    p.add_argument("node", nargs="?", help="node name")
    p.add_argument("-f", "--follow", action="store_true", help="follow new entries")
    p.add_argument("-n", "--limit", type=int, default=20, metavar="N",
                   help="number of entries to show (default: 20)")
    p.set_defaults(_handler=_cmd_logs)

    p = sub.add_parser("config", help="show or edit configuration")
    p.set_defaults(_handler=_cmd_config)
    config_sub = p.add_subparsers(dest="config_action", metavar="ACTION")
    config_sub.add_parser("show", help="show current configuration (default)")
    config_sub.add_parser("init", help="create the default config file")
    cs = config_sub.add_parser("set", help="set a config value")
    cs.add_argument("key")
    cs.add_argument("value")

    p = sub.add_parser("service", help="install Armada as a system service")
    p.set_defaults(_handler=_cmd_service)
    service_sub = p.add_subparsers(dest="service_action", metavar="ACTION")
    service_sub.add_parser("install", help="install launchd/systemd service")

    p = sub.add_parser("setup", help="install agent skills, hooks, and MCP config")
    p.set_defaults(_handler=_cmd_setup)

    p = sub.add_parser("doctor", help="diagnose and clean up local state")
    p.add_argument("--nuke", action="store_true",
                   help="kill all Armada tmux sessions and reset the DB")
    p.set_defaults(_handler=_cmd_doctor)

    p = sub.add_parser("token", help="print the auth token")
    p.add_argument("--qr", action="store_true", help="show a scannable QR code")
    p.add_argument("--lan", action="store_true", help="use the LAN IP in the QR URL")
    p.set_defaults(_handler=_cmd_token)

    p = sub.add_parser("agents", help="show detected agent CLIs and versions")
    p.add_argument("--json", action="store_true", help="output JSON")
    p.set_defaults(_handler=_cmd_agents)

    p = sub.add_parser("mcp", help="run the MCP server (stdio)")
    p.set_defaults(_handler=_cmd_mcp)

    p = sub.add_parser("report", help="report node status (used by agent hooks)")
    p.add_argument("status", choices=["active", "idle", "pending", "error"])
    p.add_argument("message", nargs="?", default="")
    p.add_argument("--options", metavar="JSON", help="permission options as a JSON array")
    p.set_defaults(_handler=_cmd_report)

    p = sub.add_parser("demodb", help="seed a demo database for recordings")
    p.set_defaults(_handler=_cmd_demodb)
    demodb_sub = p.add_subparsers(dest="demodb_action", metavar="ACTION")
    ds = demodb_sub.add_parser("seed", help="seed the demo database (default)")
    ds.add_argument("--force", action="store_true", help="allow a non-demo DB path")
    demodb_sub.add_parser("path", help="print the active database path")

    p = sub.add_parser("version", help="print the Armada version")
    p.set_defaults(_handler=_cmd_version)

    return parser


def main(argv: list[str] | None = None):
    global _COLOR_MODE

    raw = list(sys.argv[1:] if argv is None else argv)
    opts, args = _extract_global_flags(raw)

    if opts.get("no_color"):
        _COLOR_MODE = "never"
    elif opts.get("color"):
        _COLOR_MODE = "always"
    else:
        _COLOR_MODE = "auto"

    if opts.get("version"):
        print(f"armada {constants.VERSION}")
        return 0

    if not args:
        args = ["start"]

    parser = _build_parser()
    ns = parser.parse_args(args)
    for key, value in opts.items():
        if key != "version":
            setattr(ns, key, value)

    handler = getattr(ns, "_handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return handler(ns)


# --- Command handlers ---

def _cmd_start(ns):
    if not shutil.which("tmux"):
        _print_tmux_error()
        sys.exit(1)
    existing = _get_pid_from_port(constants.DEFAULT_PORT)
    if existing:
        _warn(f"Armada is already running (PID {existing}).")
        print(f"  {_style('Dashboard:', 'dim')} http://127.0.0.1:{constants.DEFAULT_PORT}")
        print(f"  {_style('Login:', 'dim')}     armada token --qr")
        print(f"  {_style('Restart:', 'dim')}   armada stop && armada")
        return
    from .server import _ensure_token, start_server
    _ensure_token(keep=True)
    _print_startup_info(lan=ns.lan, qr=ns.qr)
    start_server(
        daemon=not ns.foreground,
        open_browser=not ns.no_browser,
        lan=ns.lan,
        keep_token=ns.keep_token,
    )


def _cmd_stop(ns):
    _stop_server()


def _cmd_status(ns):
    _status(json_output=ns.json)


def _cmd_nodes(ns):
    if ns.watch:
        _watch_nodes()
        return
    _print_nodes(include_dead=ns.all, json_output=ns.json)


def _cmd_watch(ns):
    _watch_cmd([])


def _cmd_create(ns):
    subargs = ["--project", ns.project] if ns.project else []
    if ns.name:
        subargs += ["--name", ns.name]
    if ns.agent:
        subargs += ["--agent", ns.agent]
    if ns.parent is not None:
        subargs += ["--parent", str(ns.parent)]
    if ns.prompt:
        subargs += ["--prompt", ns.prompt]
    _create_cmd(subargs)


def _cmd_attach(ns):
    if ns.split and ns.name:
        _attach_split(ns.name)
    elif ns.name:
        _attach_node(ns.name)
    else:
        from .server import _ensure_token, start_server
        _ensure_token(keep=True)
        _print_startup_info(lan=ns.lan, qr=ns.qr)
        start_server(daemon=False, open_browser=False, lan=ns.lan)


def _cmd_restart(ns):
    _restart_cmd([ns.target])


def _cmd_projects(ns):
    action = ns.projects_action or "list"
    if action == "add":
        args = ["add", ns.path]
        if ns.name:
            args += ["--name", ns.name]
        if ns.id:
            args += ["--id", ns.id]
        _projects_cmd(args)
    elif action == "scan":
        _projects_cmd(["scan"])
    elif action == "rm":
        _projects_cmd(["rm", ns.id])
    else:
        _projects_cmd(["list"])


def _cmd_logs(ns):
    subargs = []
    if ns.node:
        subargs.append(ns.node)
    if ns.follow:
        subargs.append("--follow")
    subargs += ["--limit", str(ns.limit)]
    _logs_cmd(subargs)


def _cmd_config(ns):
    action = ns.config_action or "show"
    if action == "init":
        _config(["init"])
    elif action == "set":
        _config(["set", ns.key, ns.value])
    else:
        _config([])


def _cmd_service(ns):
    _service_cmd(["install"] if ns.service_action == "install" else [])


def _cmd_setup(ns):
    _setup_skills()


def _cmd_doctor(ns):
    _doctor(nuke=ns.nuke)


def _cmd_token(ns):
    _print_token(qr=ns.qr, lan=ns.lan)


def _cmd_agents(ns):
    rows = []
    for binary, label in (
        ("opencode", "OpenCode"),
        ("claude", "Claude Code"),
        ("tmux", "tmux"),
    ):
        path = shutil.which(binary)
        version = ""
        if path:
            version_args = [path, "-V"] if binary == "tmux" else [path, "--version"]
            try:
                result = subprocess.run(
                    version_args, check=False, capture_output=True, text=True, timeout=3,
                )
                output = (result.stdout or result.stderr).strip()
                version = output.splitlines()[0] if output else ""
            except Exception:
                version = ""
        rows.append({
            "id": binary,
            "label": label,
            "available": bool(path),
            "path": path or "",
            "version": version,
        })

    if ns.json:
        print(json.dumps(rows, indent=2))
        return

    _header("Agent CLIs", "detected on PATH")
    _table(
        ["AGENT", "STATUS", "VERSION", "PATH"],
        [[
            row["label"],
            _style("installed", "green", "bold") if row["available"]
            else _style("missing", "dim"),
            row["version"] or "-",
            _short_path(row["path"]) if row["path"] else "-",
        ] for row in rows],
    )
    print()
    print(
        f"  {_style('Install integrations with:', 'dim')} "
        f"{_style('armada setup', 'bold')}"
    )


def _cmd_mcp(ns):
    from .mcp_server import main as mcp_main
    mcp_main()


def _cmd_report(ns):
    subargs = [ns.status, ns.message]
    if ns.options:
        subargs += ["--options", ns.options]
    _report_cmd(subargs)


def _cmd_demodb(ns):
    action = ns.demodb_action or "seed"
    if action == "path":
        _demodb_cmd(["path"])
    else:
        subargs = ["seed"]
        if getattr(ns, "force", False):
            subargs.append("--force")
        _demodb_cmd(subargs)


def _cmd_version(ns):
    print(f"armada {constants.VERSION}")


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
    local_url = "http://127.0.0.1:9100"
    print(f"\n{_style('⚓ Armada is starting', 'bold', 'cyan')}")
    print(f"  {_style('Dashboard:', 'dim')} {_hyperlink(local_url)}")
    print(f"  {_style('Login:', 'dim')}     armada token --qr")
    if lan:
        ip = _lan_ip()
        print(f"  {_style('LAN:', 'dim')}       {_hyperlink(f'http://{ip}:9100')}")
    if qr:
        print(f"  {_style('Pair a device:', 'dim')} armada token --qr")
    print()


def _print_token(qr: bool = False, lan: bool = False):
    token = _read_token()
    if not token:
        _err("No token found.")
        _info("Start Armada first with: armada start")
        sys.exit(1)

    if qr:
        try:
            ticket = _api_get("/api/pair-ticket")["ticket"]
        except Exception as e:
            if getattr(e, "code", None) == 404:
                _err("The running Armada server is an older version.")
                _info("Restart it with: armada stop && armada")
            else:
                _err("Armada server is not reachable.")
                _info("Start it first with: armada")
            sys.exit(1)
        import qrcode
        host = _lan_ip() if lan else "127.0.0.1"
        url = f"http://{host}:9100/?ticket={ticket}"
        _header("Armada token", "scan to open the dashboard (valid for 60s)")
        print(f"  {_hyperlink(url)}")
        print()
        qr_code = qrcode.QRCode()
        qr_code.add_data(url)
        qr_code.print_ascii()
        print()
    else:
        # Keep this line machine-readable: `armada token` is often piped.
        print(token)


def _stop_server():
    pid_file = os.path.expanduser("~/.armada/server.pid")
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        _ok(f"Stopped Armada server (PID {pid}).")
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
            _ok(f"Stopped Armada server (PID {found_pid}, found via port).")
            return
        except ProcessLookupError:
            pass

    _warn("No running Armada server found.")


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
        _header("Configuration", _short_path(config.CONFIG_PATH))
        for key, value in cfg.items():
            if isinstance(value, list):
                print(f"  {_style(key, 'cyan')}:")
                for item in value:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            print(f"    {_style(k, 'dim')}: {v}")
                    else:
                        print(f"    {_style('-', 'dim')} {item}")
            else:
                print(f"  {_style(key, 'cyan')}: {value}")
    elif subargs[0] == "init":
        config.init_config()
        _ok(f"Config initialized at {_short_path(config.CONFIG_PATH)}")
    elif subargs[0] == "set" and len(subargs) >= 3:
        key = subargs[1]
        val_str = " ".join(subargs[2:])
        cfg = config.get_all()
        valid_keys = config.DEFAULTS.keys()
        if key not in valid_keys:
            _err(f"Unknown key: {key}. Valid keys: {', '.join(valid_keys)}")
            sys.exit(1)
        default_value = config.DEFAULTS[key]
        if isinstance(default_value, bool):
            cfg[key] = val_str.lower() in ("true", "1", "yes")
        elif isinstance(default_value, int):
            try:
                cfg[key] = int(val_str)
            except ValueError:
                _err(f"Invalid integer: {val_str}")
                sys.exit(1)
        elif isinstance(default_value, float):
            try:
                cfg[key] = float(val_str)
            except ValueError:
                _err(f"Invalid float: {val_str}")
                sys.exit(1)
        elif isinstance(default_value, list):
            cfg[key] = val_str.replace(",", " ").split()
        else:
            cfg[key] = val_str
        config.write_config(cfg)
        _ok(f"{key} = {cfg[key]}")
    else:
        print("Usage: armada config [init|show|set <key> <value>]")
        print("  armada config              Show current configuration")
        print("  armada config init          Create default config file")
        print("  armada config set <key> <v> Set a config value")
        print(f"\nConfig file: {config.CONFIG_PATH}")


def _setup_skills():
    if not shutil.which("tmux"):
        _err("tmux is not installed. Armada requires tmux to manage agent sessions.")
        print(f"  {_style('Install it with:', 'dim')}", file=sys.stderr)
        if platform.system() == "Darwin":
            print("    brew install tmux", file=sys.stderr)
        elif platform.system() == "Linux":
            print("    sudo apt install tmux   (Ubuntu/Debian)", file=sys.stderr)
            print("    sudo dnf install tmux   (Fedora)", file=sys.stderr)
        else:
            print("    See https://github.com/tmux/tmux/wiki/Installing", file=sys.stderr)
        sys.exit(1)

    from .infrastructure.deployment import install_skills_to_user, deploy_claude_hooks

    # Check bundled skills first (pip install), then repo root (dev)
    skill_dir = os.path.join(os.path.dirname(__file__), "skills")
    if not os.path.isdir(skill_dir):
        skill_dir = os.path.join(os.path.dirname(__file__), "..", "skills")
    if not os.path.isdir(skill_dir):
        _err("Skills directory not found. Is armada-ai installed correctly?")
        sys.exit(1)

    skill_dir = os.path.abspath(skill_dir)
    _header("Armada setup")
    _info(f"Installing skills from {_short_path(skill_dir)}")

    token = _read_token()

    if token:
        os.environ["ARMADA_AUTH_TOKEN"] = token
        _ok("ARMADA_AUTH_TOKEN set")

    installed = install_skills_to_user()
    _ok(f"Skills installed to: {', '.join(_short_path(p) for p in installed)}")

    claude_hooks = os.path.expanduser("~/.claude/hooks")
    if os.path.isdir(claude_hooks):
        deploy_claude_hooks(os.path.expanduser("~"))
        _ok(f"Claude Code hooks deployed to {_short_path(claude_hooks)}")
    else:
        _info("Claude Code hooks directory not found (skip)")


def _status(json_output: bool = False):
    try:
        info = _api_get("/api/info")
        summary = _api_get("/api/stats/summary")
    except Exception:
        if json_output:
            print(json.dumps({"status": "down"}))
        else:
            _err("Armada server is not reachable")
            print(
                f"  {_style('Start it with:', 'dim')} {_style('armada', 'bold')}",
                file=sys.stderr,
            )
        return

    data = {
        "status": "ok",
        "version": info.get("version", "?"),
        "uptime": info.get("uptime", 0),
        "agents": summary.get("total_agents", 0),
        "active": summary.get("active", 0),
        "pending": summary.get("pending", 0),
        "idle": summary.get("idle", 0),
    }

    if json_output:
        print(json.dumps(data, indent=2))
        return

    uptime = data.get("uptime", 0)
    total = data.get("agents", 0)
    counts = []
    for status in ("active", "pending", "idle"):
        marker, colour = _status_marker(status)
        counts.append(
            f"{_style(marker, colour)} {data.get(status, 0)} {status}"
        )

    _header("Armada status")
    print(
        f"  {_style('Server:', 'dim')} "
        f"{_style('running', 'green', 'bold')} (v{data.get('version', '?')})"
    )
    print(
        f"  {_style('Uptime:', 'dim')} "
        f"{_fmt_duration(uptime)} ({int(uptime)}s)"
    )
    print(
        f"  {_style('Agents:', 'dim')} {total}  " + "  ".join(counts)
    )
    print(
        f"  {_style('Dashboard:', 'dim')} "
        f"{_style(f'http://127.0.0.1:{constants.DEFAULT_PORT}', 'cyan')}"
    )



def _doctor(nuke: bool = False):
    import sqlite3
    import glob
    from . import tmux as _tmux_mod

    _header("Armada Doctor")

    # 1. Check tmux
    _section("[1] Tmux sessions")
    try:
        running = _tmux_mod.running_window_names()
        if running:
            _info(f"Live windows: {_style(', '.join(running), 'bold')}")
        else:
            _info("No armada windows found")
    except Exception as e:
        _err(f"Error checking tmux: {e}")

    # 2. Check server
    _section("[2] Server process")
    found_pid = _get_pid_from_port(constants.DEFAULT_PORT)
    pid_file = os.path.expanduser("~/.armada/server.pid")
    pid_file_pid = None
    try:
        with open(pid_file) as f:
            pid_file_pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        pass

    if found_pid:
        _ok(f"Listening on port {constants.DEFAULT_PORT} (PID {found_pid})")
    elif pid_file_pid:
        try:
            os.kill(pid_file_pid, 0)
            _info(f"PID file says {pid_file_pid} (but not on port {constants.DEFAULT_PORT})")
        except OSError:
            _warn(f"PID file says {pid_file_pid} (process is dead — cleaning up)")
            os.remove(pid_file)
    else:
        _info("Not running")

    if nuke:
        _section("--nuke: Killing all armada tmux sessions and resetting state")
        try:
            subprocess.run(["tmux", "kill-server"], capture_output=True, timeout=5)
        except Exception:
            pass
        db_path = constants.DB_PATH
        if os.path.exists(db_path):
            os.remove(db_path)
            _ok(f"Removed {os.path.basename(db_path)}")
        if os.path.exists(pid_file):
            os.remove(pid_file)
            _ok("Removed PID file")
        log_dir = os.path.expanduser("~/.armada/logs")
        if os.path.isdir(log_dir):
            for f in os.listdir(log_dir):
                os.remove(os.path.join(log_dir, f))
            _ok("Cleared logs")
        _ok("Done. Start fresh with: armada")
        sys.exit(0)

    # 3. Sync DB with tmux
    _section("[3] Database sync")
    db_path = constants.DB_PATH
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        live_nodes = conn.execute(
            "SELECT id, name FROM nodes WHERE status != 'dead'"
        ).fetchall()
        running_names = _tmux_mod.running_window_names()
        stale = [(row["id"], row["name"]) for row in live_nodes if row["name"] not in running_names]
        if stale:
            for nid, name in stale:
                conn.execute(
                    "UPDATE nodes SET status='dead' WHERE id=?",
                    (nid,)
                )
            conn.commit()
            _ok(f"Marked {len(stale)} node(s) as dead: {', '.join(n for _, n in stale)}")
        else:
            _ok("All DB nodes have live tmux windows")
        conn.close()
    else:
        _info("No DB found (nothing to sync)")

    # 4. Clean up /tmp/_armada_* temp files
    _section("[4] Temp files (/tmp/_armada_*)")
    temps = glob.glob("/tmp/_armada_*")
    if temps:
        for f in temps:
            try:
                os.remove(f)
            except OSError:
                pass
        _ok(f"Removed {len(temps)} file(s)")
    else:
        _info("None found")

    # 5. Clean up stale hooks
    _section("[5] Stale hook files")
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
            _ok(f"Removed {removed} stale hook file(s)")
        else:
            _info("None found")
    else:
        _info("No hooks directory")

    _ok("Done.")


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


def _api_delete(path: str):
    import json
    import urllib.request
    token = _read_token()
    req = urllib.request.Request(
        f"http://127.0.0.1:9100{path}",
        method="DELETE",
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


def _print_nodes(include_dead: bool = False, json_output: bool = False):
    path = "/api/tree" if include_dead else "/api/tree?hide_dead=true"
    try:
        tree = _api_get(path)
    except Exception as e:
        print(f"Failed to reach Armada server: {e}", file=sys.stderr)
        sys.exit(1)

    if json_output:
        print(json.dumps(tree, indent=2))
        return

    def _collect(nodes, depth=0):
        rows = []
        for n in nodes:
            rows.append({
                "id": n["id"],
                "name": n["name"],
                "status": n["status"],
                "colour": n.get("colour", "#8b949e"),
                "project": n.get("project_label_name", "") or "",
                "message": n.get("latest_message", "") or "",
                "total_cost": n.get("total_cost", 0) or 0,
                "depth": depth,
            })
            if n.get("children"):
                rows.extend(_collect(n["children"], depth + 1))
        return rows

    rows = _collect(tree)
    if not rows:
        _header("Armada nodes")
        print(f"  {_style('No agents yet.', 'dim')}")
        print(f"  Create one with: {_style('armada create -p <project>', 'bold')}")
        return

    active = sum(1 for r in rows if r["status"] == "active")
    pending = sum(1 for r in rows if r["status"] == "pending")
    idle = sum(1 for r in rows if r["status"] == "idle")
    _header(
        "Armada nodes",
        f"{len(rows)} agents · {active} active · {pending} pending · {idle} idle",
    )

    show_cost = any(r["total_cost"] > 0 for r in rows)
    table_rows = []
    pending_names = []
    for r in rows:
        name = ("  " * r["depth"]) + r["name"]
        if len(name) > 30:
            name = name[:29] + "…"
        if r["status"] == "dead":
            name = _style(name, "dim")

        project = r["project"][:18]
        message = " ".join(r["message"].split())[:60]
        if r["status"] == "dead":
            project = _style(project, "dim")
            message = _style(message, "dim")
        if r["status"] == "pending":
            pending_names.append(r["name"])

        row = [_status_cell(r["status"]), name, project, message]
        if show_cost:
            row.append(f"${r['total_cost']:.2f}")
        table_rows.append(row)

    headers = ["STATUS", "NAME", "PROJECT", "MESSAGE"]
    aligns = ["left", "left", "left", "left"]
    if show_cost:
        headers.append("COST")
        aligns.append("right")
    _table(headers, table_rows, aligns=aligns)

    if pending_names:
        print()
        _warn(f"Pending: {', '.join(pending_names)}")


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


def _escape_applescript(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _focus_attached_node(name):
    """Focus the iTerm tab/window already attached to the given node name."""
    import subprocess
    system = platform.system()
    if system != "Darwin":
        _focus_iterm()
        return

    safe_name = _escape_applescript(name)
    script = f'''
    tell application "iTerm"
        repeat with w in windows
            repeat with t in tabs of w
                repeat with s in sessions of t
                    if name of s contains "{safe_name}" then
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
                _watch_draw_projects(projects, selected, tw, has_pending, pending_names, _status_msg)

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
                elif ch == 'n':
                    err = _watch_add_project(fd, old_settings)
                    if err:
                        _status_msg = err
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


def _watch_draw_projects(projects, selected, tw, has_pending=False, pending_names=None, status_msg=""):
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

    if status_msg:
        is_error = status_msg.startswith("Failed")
        color = "\033[31m" if is_error else "\033[32m"
        sys.stdout.write(f"\n{color}  {status_msg}\033[0m\n")

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
        {"label": "Path", "value": "", "type": "text", "required": True},
        {"label": "[ Save ]", "type": "button"},
    ]
    result = _watch_form(fd, old_settings, "New Project", fields)
    if not result or not result["Path"]:
        return None
    try:
        _api_post("/api/project-labels", {"path": result["Path"]})
    except Exception as e:
        return f"Failed: {e}"
    return None


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
    p.add_argument("--project", "-p",
                   help="Project folder or label ID (default: current directory)")
    p.add_argument("--agent", "-a", default="auto",
                   choices=["auto", "opencode", "claude", "bash"],
                   help="Agent type (default: auto)")
    p.add_argument("--parent", "-P", type=int, help="Parent node ID")
    p.add_argument("--prompt", "-m", help="Initial prompt to send to the agent")
    try:
        ns = p.parse_args(subargs)
    except SystemExit:
        return

    body = {"agent_type": ns.agent}
    value = ns.project or os.getcwd()
    expanded = os.path.expanduser(value)
    if ns.project and not os.path.isdir(expanded) and "/" not in value and "~" not in value:
        body["project_label_id"] = value
    else:
        body["project_path"] = os.path.abspath(expanded)
    if ns.name:
        body["name"] = ns.name.replace(".", "-")
    if ns.parent:
        body["parent_id"] = ns.parent
    if ns.prompt:
        body["initial_prompt"] = ns.prompt

    try:
        result = _api_post("/api/nodes", body)
        _ok(f"Created node {result['name']} (id={result['id']})")
    except Exception as e:
        resp = ""
        try:
            resp = str(e.read(), "utf-8")[:200]
        except Exception:
            pass
        _err(f"Failed: {e}")
        if resp:
            print(f"  {_style(resp, 'dim')}", file=sys.stderr)
        sys.exit(1)


def _projects_cmd(subargs: list[str]):
    if subargs and subargs[0] == "add":
        parser = argparse.ArgumentParser(prog="armada projects add", add_help=False)
        parser.add_argument("path")
        parser.add_argument("--name")
        parser.add_argument("--id")
        ns, _ = parser.parse_known_args(subargs[1:])
        body = {"path": ns.path}
        if ns.name:
            body["name"] = ns.name
        if ns.id:
            body["id"] = ns.id
        try:
            label = _api_post("/api/project-labels", body)
            _ok(f"Added project {label.get('id') or body.get('id') or body['path']}")
        except Exception as e:
            _err(f"Failed: {e}")
            sys.exit(1)
        return

    if subargs and subargs[0] == "scan":
        try:
            data = _api_get("/api/project-labels/discover")
        except Exception as e:
            _err(f"Failed: {e}")
            sys.exit(1)
        found = [p for p in data.get("projects", []) if not p.get("id")]
        _header("Discovered", f"{len(found)} not registered")
        if not found:
            print(f"  {_style('Nothing new under ' + ', '.join(data.get('roots', [])), 'dim')}")
            return
        _table(["NAME", "PATH"], [[p["name"], _short_path(p["path"])] for p in found])
        print(f"  Add one with: {_style('armada projects add <path>', 'bold')}")
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
            _ok(f"Removed project {subargs[1]}")
        except Exception as e:
            _err(f"Failed: {e}")
            sys.exit(1)
        return

    try:
        labels = _api_get("/api/project-labels")
    except Exception as e:
        _err(f"Failed: {e}")
        sys.exit(1)

    _header("Projects", f"{len(labels)} registered")
    if not labels:
        print(f"  {_style('No projects.', 'dim')}")
        print(f"  Add one with: {_style('armada projects add <path>', 'bold')}")
        return

    _table(
        ["ID", "NAME", "PATH"],
        [[lb["id"], lb["name"], _short_path(lb["path"])] for lb in labels],
    )


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
        _ok(f"Attached to {node['name']}")
    except Exception as e:
        resp_body = ""
        try:
            resp_body = str(e.read(), "utf-8")[:200]
        except Exception:
            pass
        _err(f"Failed to attach: {e}")
        if resp_body:
            print(f"  {_style(resp_body, 'dim')}", file=sys.stderr)
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


def _logs_cmd(subargs: list[str]):
    import time
    import json
    from datetime import datetime

    follow = "--follow" in subargs or "-f" in subargs
    flags_to_strip = {"--follow", "-f"}

    # Parse --limit / -n
    limit = 20
    clean_args = []
    i = 0
    while i < len(subargs):
        if subargs[i] in ("--limit", "-n"):
            if i + 1 < len(subargs):
                try:
                    limit = int(subargs[i + 1])
                except ValueError:
                    print(f"Invalid limit: {subargs[i + 1]}", file=sys.stderr)
                    sys.exit(1)
                i += 2
                continue
        elif subargs[i] not in flags_to_strip:
            clean_args.append(subargs[i])
        i += 1

    if not clean_args:
        print("Usage: armada logs <node-name> [-f|--follow] [-n|--limit N]", file=sys.stderr)
        sys.exit(1)

    node_name = clean_args[0]
    log_path = os.path.join(constants.LOGS_DIR, f"{node_name}.jsonl")

    if not os.path.exists(log_path):
        print(f"No log file found for node '{node_name}'.", file=sys.stderr)
        print(f"  Expected: {log_path}", file=sys.stderr)
        # List available nodes
        if os.path.isdir(constants.LOGS_DIR):
            available = [f[:-6] for f in os.listdir(constants.LOGS_DIR)
                        if f.endswith(".jsonl") and not f.startswith("_")]
            if available:
                print(f"  Available nodes: {', '.join(sorted(available))}", file=sys.stderr)
        sys.exit(1)

    def _format_entry(entry: dict) -> str:
        ts = entry.get("ts", 0)
        dt = _style(datetime.fromtimestamp(ts).strftime("%H:%M:%S"), "dim")
        etype = entry.get("type", "?")
        data = entry.get("data", {})
        # Build a concise message from data
        if etype == "report":
            status = data.get("status", "")
            marker = _status_cell(status) if status else ""
            msg = f"{marker} {data.get('message', '')}".strip()
        elif etype == "create":
            msg = (
                f"{_style('agent', 'dim')}={data.get('agent_type', '?')} "
                f"{_style('project', 'dim')}={data.get('project', '?')}"
            )
        elif etype == "send":
            msg = data.get("command", "")
        elif etype == "output":
            msg = data.get("content", "")[:100]
        elif etype == "health":
            msg = _style("dead", "red") if data.get("dead") else _style("alive", "green")
        else:
            msg = json.dumps(data) if data else ""
        return f"{dt}  {_style(f'{etype:<10}', 'bold', 'cyan')}  {msg}"

    # Read last N lines
    try:
        with open(log_path) as f:
            lines = f.readlines()
    except IOError as e:
        _err(f"Error reading log: {e}")
        sys.exit(1)

    tail_lines = lines[-limit:]
    _header(f"Logs · {node_name}", f"{len(tail_lines)} entries")
    for line in tail_lines:
        try:
            entry = json.loads(line)
            print(_format_entry(entry))
        except json.JSONDecodeError:
            continue

    if not follow:
        return

    # Follow mode: watch for new lines
    try:
        with open(log_path) as f:
            # Seek to end
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    try:
                        entry = json.loads(line)
                        print(_format_entry(entry))
                    except json.JSONDecodeError:
                        pass
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def _restart_cmd(subargs: list[str]):
    if not subargs:
        print("Usage: armada restart <node-name-or-id>", file=sys.stderr)
        sys.exit(1)

    search = subargs[0]
    node = _find_node(search)
    if not node:
        sys.exit(1)

    node_id = node["id"]
    node_name = node["name"]
    project_label_id = node.get("project_label_id", "")
    agent_type = node.get("agent_type", "auto")

    # Kill the node
    _info(f"Killing {node_name} (id={node_id})...")
    try:
        _api_delete(f"/api/nodes/{node_id}")
    except Exception as e:
        _err(f"Failed to kill node: {e}")
        sys.exit(1)

    # Recreate with same config
    _info(f"Recreating with project={project_label_id} agent_type={agent_type}...")
    body = {
        "project_label_id": project_label_id,
        "agent_type": agent_type,
    }
    try:
        result = _api_post("/api/nodes", body)
        _ok(f"Created new node: {result['name']} (id={result['id']})")
    except Exception as e:
        resp = ""
        try:
            resp = str(e.read(), "utf-8")[:200]
        except Exception:
            pass
        _err(f"Failed to create node: {e}")
        if resp:
            print(f"  {_style(resp, 'dim')}", file=sys.stderr)
        sys.exit(1)


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
