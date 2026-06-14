import os

DATA_DIR = os.path.expanduser("~/.armada")
DB_PATH = os.path.join(DATA_DIR, "armada.db")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
HOOKS_DIR = os.path.join(DATA_DIR, "hooks")
WORKSPACES_DIR = os.path.join(DATA_DIR, "workspaces")
CONFIG_PATH = os.path.join(DATA_DIR, "config.yaml")
PID_FILE = os.path.join(DATA_DIR, "server.pid")
TOKEN_FILE = os.path.join(DATA_DIR, "token")

VERSION = "0.2.1"

MAX_RETRIES = 5
RETRY_BASE_DELAY = 0.05

MAX_REPORTS_PER_NODE = 200
PRUNE_THRESHOLD = 50

MAX_RESTARTS = 3
DEFAULT_PORT = 9100
DEFAULT_HOST = "127.0.0.1"
DEFAULT_HEALTH_INTERVAL = 15
