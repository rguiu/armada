"""Database persistence layer — refactored from db.py.

Uses domain models for return types. Non-db concerns (restart counts,
project JSON sync) live alongside but are clearly separated.
"""
import json
import os
import sqlite3
import threading
import time

from .. import constants
from ..domain.models import Node, ProjectLabel

_write_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()
_MAX_RETRIES = constants.MAX_RETRIES
_RETRY_BASE_DELAY = constants.RETRY_BASE_DELAY

_restart_counts: dict[str, int] = {}


# --- Connection management ---

def _ensure_dir():
    os.makedirs(constants.DATA_DIR, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        _ensure_dir()
        _conn = sqlite3.connect(constants.DB_PATH, timeout=30, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA busy_timeout=30000")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA cache_size=-8000")
        _conn.row_factory = sqlite3.Row
        return _conn


def close_connection():
    global _conn
    with _conn_lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


def _retry(fn, *, write: bool = False):
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            if write:
                with _write_lock:
                    return fn()
            return fn()
        except sqlite3.OperationalError as e:
            last_error = e
            if "locked" not in str(e).lower():
                raise
            time.sleep(_RETRY_BASE_DELAY * (attempt + 1))
    raise last_error


# --- Schema init ---

def init_db():
    conn = _get_conn()
    with _write_lock:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS project_labels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
                project_label_id TEXT REFERENCES project_labels(id),
                tmux_pane_id TEXT,
                colour TEXT NOT NULL,
                status TEXT DEFAULT 'idle',
                agent_type TEXT DEFAULT 'auto',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                killed_at TEXT,
                hidden_at TEXT,
                total_tokens_in INTEGER DEFAULT 0,
                total_tokens_out INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS status_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                message TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_reports_node
                ON status_reports(node_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_killed ON nodes(killed_at);
            CREATE INDEX IF NOT EXISTS idx_nodes_hidden ON nodes(hidden_at);
            CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project_label_id);

            CREATE TABLE IF NOT EXISTS hourly_stats (
                hour TEXT PRIMARY KEY,
                active_agents INTEGER NOT NULL DEFAULT 0,
                total_agents INTEGER NOT NULL DEFAULT 0,
                total_cost REAL NOT NULL DEFAULT 0.0,
                total_tokens_in INTEGER NOT NULL DEFAULT 0,
                total_tokens_out INTEGER NOT NULL DEFAULT 0,
                snapshot_ts TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    _migrate()
    _sync_projects_from_json()
    _migrate_hourly_stats()


def _migrate():
    conn = _get_conn()
    with _write_lock:
        for col, col_type in [
            ("hidden_at", "TEXT"),
            ("total_tokens_in", "INTEGER DEFAULT 0"),
            ("total_tokens_out", "INTEGER DEFAULT 0"),
            ("total_cost", "REAL DEFAULT 0.0"),
            ("log_count", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE nodes ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
    try:
        conn.execute("ALTER TABLE status_reports ADD COLUMN options TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass


# --- Project Labels ---

def add_project_label(id: str, name: str, path: str):
    def _do():
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO project_labels (id, name, path) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, path = excluded.path",
                (id, name, path),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            existing = conn.execute(
                "SELECT id FROM project_labels WHERE path = ? AND id != ?", (path, id)
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Path '{path}' is already registered as '{existing[0]}'. "
                    f"Remove it first."
                ) from e
            raise
    _retry(_do, write=True)
    _save_projects_to_json()


def delete_project_label(id: str):
    def _do():
        conn = _get_conn()
        conn.execute("DELETE FROM project_labels WHERE id = ?", (id,))
        conn.commit()
    _retry(_do, write=True)
    _save_projects_to_json()


def list_project_labels() -> list[ProjectLabel]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, path FROM project_labels ORDER BY name"
    ).fetchall()
    return [ProjectLabel(id=r[0], name=r[1], path=r[2]) for r in rows]


def get_project_label_path(label_id: str) -> str | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT path FROM project_labels WHERE id = ?", (label_id,)
    ).fetchone()
    return row[0] if row else None


# --- Nodes ---

def create_node(name: str, colour: str, parent_id: int | None = None,
                project_label_id: str | None = None,
                tmux_pane_id: str | None = None,
                agent_type: str = "auto") -> int:
    def _do():
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO nodes (name, colour, parent_id, project_label_id, "
                "tmux_pane_id, agent_type) VALUES (?, ?, ?, ?, ?, ?)",
                (name, colour, parent_id, project_label_id, tmux_pane_id, agent_type),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE nodes SET killed_at = NULL, hidden_at = NULL, status = 'idle', "
                "colour = ?, parent_id = ?, project_label_id = ?, tmux_pane_id = ?, "
                "agent_type = ? WHERE name = ?",
                (colour, parent_id, project_label_id, tmux_pane_id, agent_type, name),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM nodes WHERE name = ?", (name,)
            ).fetchone()
            return row[0]
    return _retry(_do, write=True)


def kill_node(node_id: int) -> list[dict]:
    killed = []
    def _do():
        conn = _get_conn()
        stack = [node_id]
        while stack:
            current = stack.pop()
            children = conn.execute(
                "SELECT id FROM nodes WHERE parent_id = ? AND killed_at IS NULL",
                (current,)
            ).fetchall()
            for child in children:
                stack.append(child[0])
            name_row = conn.execute(
                "SELECT name FROM nodes WHERE id = ?", (current,)
            ).fetchone()
            killed.append({"id": current, "name": name_row[0] if name_row else ""})
            conn.execute(
                "UPDATE nodes SET killed_at = datetime('now'), status = 'dead' "
                "WHERE id = ?", (current,)
            )
        conn.commit()
    _retry(_do, write=True)
    return killed


def hide_node(node_id: int) -> list[dict]:
    hidden = []
    def _do():
        conn = _get_conn()
        stack = [node_id]
        while stack:
            current = stack.pop()
            children = conn.execute(
                "SELECT id FROM nodes WHERE parent_id = ? AND hidden_at IS NULL",
                (current,)
            ).fetchall()
            for child in children:
                stack.append(child[0])
            name_row = conn.execute(
                "SELECT name FROM nodes WHERE id = ?", (current,)
            ).fetchone()
            hidden.append({"id": current, "name": name_row[0] if name_row else ""})
            conn.execute(
                "UPDATE nodes SET hidden_at = datetime('now'), status = 'dead' "
                "WHERE id = ?", (current,)
            )
        conn.commit()
    _retry(_do, write=True)
    return hidden


def reparent_node(node_id: int, parent_id: int | None):
    def _do():
        conn = _get_conn()
        conn.execute("UPDATE nodes SET parent_id = ? WHERE id = ?", (parent_id, node_id))
        conn.commit()
    _retry(_do, write=True)


def rename_node(node_id: int, new_name: str):
    def _do():
        conn = _get_conn()
        conn.execute("UPDATE nodes SET name = ? WHERE id = ?", (new_name, node_id))
        conn.commit()
    _retry(_do, write=True)


def update_node_status(node_id: int, status: str, tmux_pane_id: str | None = None):
    def _do():
        conn = _get_conn()
        parts = ["status = ?"]
        params = [status]
        if tmux_pane_id is not None:
            parts.append("tmux_pane_id = ?")
            params.append(tmux_pane_id)
        params.append(node_id)
        conn.execute(f"UPDATE nodes SET {', '.join(parts)} WHERE id = ?", params)
        conn.commit()
    _retry(_do, write=True)


# --- Status Reports ---

_PRUNE_THRESHOLD = 50
_MAX_REPORTS_PER_NODE = 200
_last_prune: dict[int, int] = {}


def add_status_report(node_id: int, status: str, message: str | None = None,
                      options: str = ""):
    def _do():
        conn = _get_conn()
        conn.execute(
            "INSERT INTO status_reports (node_id, status, message, options) VALUES (?, ?, ?, ?)",
            (node_id, status, message, options),
        )
        conn.execute("UPDATE nodes SET status = ? WHERE id = ?", (status, node_id))
        conn.commit()
    _retry(_do, write=True)
    _prune_reports_if_needed(node_id)


def _prune_reports_if_needed(node_id: int):
    count = _last_prune.get(node_id, 0) + 1
    _last_prune[node_id] = count
    if count >= _PRUNE_THRESHOLD:
        _last_prune[node_id] = 0
        _prune_old_reports(node_id, keep=_MAX_REPORTS_PER_NODE)


def _prune_old_reports(node_id: int, keep: int = 200):
    def _do():
        conn = _get_conn()
        conn.execute("""
            DELETE FROM status_reports WHERE id IN (
                SELECT id FROM status_reports WHERE node_id = ?
                ORDER BY timestamp DESC LIMIT -1 OFFSET ?
            )
        """, (node_id, keep))
        conn.commit()
    _retry(_do, write=True)


def prune_all_old_reports(keep: int = 200):
    def _do():
        conn = _get_conn()
        conn.execute("""
            DELETE FROM status_reports WHERE id IN (
                SELECT id FROM status_reports
                ORDER BY timestamp DESC LIMIT -1 OFFSET ?
            )
        """, (keep,))
        conn.commit()
    _retry(_do, write=True)


def vacuum_db():
    def _do():
        conn = _get_conn()
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        conn.execute("PRAGMA optimize")
    _retry(_do, write=True)


# --- Hourly Stats ---

def _migrate_hourly_stats():
    conn = _get_conn()
    with _write_lock:
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hourly_stats (
                    hour TEXT PRIMARY KEY,
                    active_agents INTEGER NOT NULL DEFAULT 0,
                    total_agents INTEGER NOT NULL DEFAULT 0,
                    total_cost REAL NOT NULL DEFAULT 0.0,
                    total_tokens_in INTEGER NOT NULL DEFAULT 0,
                    total_tokens_out INTEGER NOT NULL DEFAULT 0,
                    snapshot_ts TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        except sqlite3.OperationalError:
            pass


def snapshot_stats():
    """Capture current fleet stats into hourly_stats (idempotent per hour)."""
    nodes = get_all_nodes(include_dead=False)
    active = sum(1 for n in nodes if n.status == "active")
    total = len(nodes)
    cost = sum(n.total_cost for n in nodes)
    tokens_in = sum(n.total_tokens_in for n in nodes)
    tokens_out = sum(n.total_tokens_out for n in nodes)

    import datetime
    hour_key = datetime.datetime.now().strftime("%Y-%m-%dT%H")

    def _do():
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO hourly_stats (hour, active_agents, total_agents, "
            "total_cost, total_tokens_in, total_tokens_out, snapshot_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (hour_key, active, total, cost, tokens_in, tokens_out),
        )
        conn.commit()
    _retry(_do, write=True)


def get_hourly_stats(hours: int = 24) -> list[dict]:
    """Return up to N most recent hourly stat snapshots."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM hourly_stats ORDER BY hour DESC LIMIT ?", (hours,)
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_stats_summary() -> dict:
    """Current fleet summary for dashboard stats."""
    nodes = get_all_nodes(include_dead=False)
    total = len(nodes)
    active = sum(1 for n in nodes if n.status == "active")
    pending = sum(1 for n in nodes if n.status == "pending")
    idle = sum(1 for n in nodes if n.status == "idle")
    cost = sum(n.total_cost for n in nodes)
    tokens_in = sum(n.total_tokens_in for n in nodes)
    tokens_out = sum(n.total_tokens_out for n in nodes)

    history = get_hourly_stats(24)
    return {
        "total_agents": total,
        "active": active,
        "pending": pending,
        "idle": idle,
        "total_cost": cost,
        "total_tokens_in": tokens_in,
        "total_tokens_out": tokens_out,
        "history": history,
    }



# --- Cost & Count accumulation ---

def accumulate_cost(node_id: int, tokens_in: int = 0, tokens_out: int = 0,
                    cost: float = 0.0):
    def _do():
        conn = _get_conn()
        conn.execute(
            "UPDATE nodes SET total_tokens_in = total_tokens_in + ?, "
            "total_tokens_out = total_tokens_out + ?, total_cost = total_cost + ? "
            "WHERE id = ?",
            (tokens_in, tokens_out, cost, node_id),
        )
        conn.commit()
    _retry(_do, write=True)


def increment_log_count(node_id: int, count: int = 1):
    def _do():
        conn = _get_conn()
        conn.execute(
            "UPDATE nodes SET log_count = log_count + ? WHERE id = ?",
            (count, node_id),
        )
        conn.commit()
    _retry(_do, write=True)


# --- Queries ---

def get_node(node_id: int) -> Node | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT n.*, p.name as project_label_name, p.path as project_path "
        "FROM nodes n LEFT JOIN project_labels p ON n.project_label_id = p.id "
        "WHERE n.id = ?", (node_id,)
    ).fetchone()
    return Node.from_row(dict(row)) if row else None


def get_node_by_name(name: str) -> Node | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM nodes WHERE name = ? AND killed_at IS NULL AND hidden_at IS NULL",
        (name,)
    ).fetchone()
    return Node.from_row(dict(row)) if row else None


def get_node_children(node_id: int) -> list[Node]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM nodes WHERE parent_id = ? AND killed_at IS NULL AND hidden_at IS NULL",
        (node_id,)
    ).fetchall()
    return [Node.from_row(dict(r)) for r in rows]


def get_all_nodes(include_dead: bool = True) -> list[Node]:
    conn = _get_conn()
    base = """
        SELECT n.id, n.name, n.parent_id, n.project_label_id, n.colour, n.status,
               n.agent_type, n.created_at, {} n.total_tokens_in, n.total_tokens_out,
               n.total_cost, n.log_count,
               p.name as project_label_name,
               (SELECT message FROM status_reports WHERE node_id = n.id
                 ORDER BY id DESC LIMIT 1) as latest_message,
                (SELECT options FROM status_reports WHERE node_id = n.id
                 ORDER BY id DESC LIMIT 1) as latest_options,
                (SELECT timestamp FROM status_reports WHERE node_id = n.id
                 ORDER BY id DESC LIMIT 1) as latest_report_time
        FROM nodes n
        LEFT JOIN project_labels p ON n.project_label_id = p.id
        WHERE {} n.hidden_at IS NULL
        ORDER BY n.created_at DESC
    """
    if include_dead:
        query = base.format("n.killed_at,", "")
    else:
        query = base.format("", "n.killed_at IS NULL AND")
    rows = conn.execute(query).fetchall()
    return [Node.from_row(dict(r)) for r in rows]


def get_root_nodes() -> list[Node]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, parent_id, project_label_id, colour, status, created_at "
        "FROM nodes WHERE parent_id IS NULL AND killed_at IS NULL AND hidden_at IS NULL "
        "ORDER BY created_at DESC"
    ).fetchall()
    return [Node.from_row(dict(r)) for r in rows]


def get_nodes_by_project_label_id(label_id: str) -> list[Node]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT n.id, n.name, n.colour, n.status, n.agent_type, n.created_at, "
        "n.total_tokens_in, n.total_tokens_out, n.total_cost, "
        "(SELECT message FROM status_reports WHERE node_id = n.id "
        " ORDER BY id DESC LIMIT 1) as latest_message "
        "FROM nodes n "
        "WHERE n.project_label_id = ? AND n.killed_at IS NULL AND n.hidden_at IS NULL "
        "ORDER BY n.created_at DESC",
        (label_id,),
    ).fetchall()
    return [Node.from_row(dict(r)) for r in rows]


def get_killed_nodes(limit: int = 50) -> list[Node]:
    conn = _get_conn()
    rows = conn.execute("""
        SELECT n.id, n.name, n.colour, n.agent_type, n.status,
               n.created_at, n.killed_at, n.project_label_id,
               p.name as project_label_name,
               (SELECT message FROM status_reports WHERE node_id = n.id
                 ORDER BY id DESC LIMIT 1) as latest_message
        FROM nodes n
        LEFT JOIN project_labels p ON n.project_label_id = p.id
        WHERE n.killed_at IS NOT NULL AND n.hidden_at IS NULL
        ORDER BY n.killed_at DESC LIMIT ?
    """, (limit,)).fetchall()
    return [Node.from_row(dict(r)) for r in rows]


def get_node_reports(node_id: int, limit: int = 30) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, node_id, status, message, options, timestamp FROM status_reports "
        "WHERE node_id = ? ORDER BY id DESC LIMIT ?",
        (node_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def build_tree(include_dead: bool = True) -> list[dict]:
    all_nodes = get_all_nodes(include_dead=include_dead)
    node_map: dict[int, dict] = {}
    for n in all_nodes:
        node_dict = n.as_summary()
        node_dict["children"] = []
        node_map[n.id] = node_dict

    roots = []
    for n in all_nodes:
        node_dict = node_map[n.id]
        if n.parent_id and n.parent_id in node_map:
            node_map[n.parent_id]["children"].append(node_dict)
        else:
            roots.append(node_dict)

    return roots


def existing_names() -> set[str]:
    conn = _get_conn()
    rows = conn.execute("SELECT name FROM nodes WHERE hidden_at IS NULL").fetchall()
    return {r[0] for r in rows}


def active_colours() -> list[str]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT colour FROM nodes WHERE killed_at IS NULL AND hidden_at IS NULL"
    ).fetchall()
    return [r[0] for r in rows]


# --- Recovery ---

def recover_nodes(running_names: set[str]):
    def _do():
        conn = _get_conn()
        live = conn.execute(
            "SELECT id, name FROM nodes WHERE killed_at IS NULL AND hidden_at IS NULL"
        ).fetchall()
        for row in live:
            name = row["name"]
            if name in running_names:
                continue
            conn.execute(
                "UPDATE nodes SET killed_at = datetime('now'), status = 'dead' WHERE id = ?",
                (row["id"],),
            )
        conn.commit()
    _retry(_do, write=True)


def recover_live_nodes(running_names: set[str]) -> list[Node]:
    if not running_names:
        return []
    conn = _get_conn()
    placeholders = ",".join("?" * len(running_names))
    rows = conn.execute(
        f"SELECT id, name, colour, parent_id, project_label_id, tmux_pane_id, agent_type "
        f"FROM nodes WHERE killed_at IS NULL AND hidden_at IS NULL AND name IN ({placeholders})",
        list(running_names),
    ).fetchall()
    return [Node.from_row(dict(r)) for r in rows]


# --- Restart counts (in-memory, not persisted to DB) ---

def get_restart_count_for_name(name: str) -> int:
    return _restart_counts.get(name, 0)


def increment_restart_count(name: str):
    _restart_counts[name] = _restart_counts.get(name, 0) + 1


# --- Projects JSON persistence ---

def _save_projects_to_json():
    labels = list_project_labels()
    _ensure_dir()
    with open(constants.PROJECTS_FILE, "w") as f:
        json.dump([{"id": lb.id, "name": lb.name, "path": lb.path}
                    for lb in labels], f, indent=2)


def _sync_projects_from_json():
    if not os.path.exists(constants.PROJECTS_FILE):
        _save_projects_to_json()
        return

    try:
        with open(constants.PROJECTS_FILE) as f:
            json_projects = json.load(f)
    except (json.JSONDecodeError, IOError):
        _save_projects_to_json()
        return

    db_projects = {p.id: p for p in list_project_labels()}

    for jp in json_projects:
        if not isinstance(jp, dict):
            continue
        if jp["id"] not in db_projects:
            add_project_label(jp["id"], jp["name"], jp["path"])
            continue
        db_p = db_projects[jp["id"]]
        if jp["name"] != db_p.name or jp["path"] != db_p.path:
            add_project_label(jp["id"], jp["name"], jp["path"])
            continue

    db_ids = {p.id for p in db_projects.values()}
    json_ids = {p["id"] for p in json_projects if isinstance(p, dict)}
    if db_ids != json_ids:
        _save_projects_to_json()
