import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _read_version() -> str:
    try:
        from importlib.metadata import version
        return version("armada-ai")
    except Exception:
        pass
    try:
        _dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_dir, "pyproject.toml"), "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return "unknown"


VERSION = _read_version()

DATA_DIR = os.path.expanduser("~/.armada")
DB_PATH = os.path.join(DATA_DIR, "armada.db")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
HOOKS_DIR = os.path.join(DATA_DIR, "hooks")
WORKSPACES_DIR = os.path.join(DATA_DIR, "workspaces")
CONFIG_PATH = os.path.join(DATA_DIR, "config.yaml")
PID_FILE = os.path.join(DATA_DIR, "server.pid")
TOKEN_FILE = os.path.join(DATA_DIR, "token")

MAX_RETRIES = 5
RETRY_BASE_DELAY = 0.05

MAX_REPORTS_PER_NODE = 200
PRUNE_THRESHOLD = 50

MAX_RESTARTS = 3
DEFAULT_PORT = 9100
DEFAULT_HOST = "127.0.0.1"
DEFAULT_HEALTH_INTERVAL = 15
