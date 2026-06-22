"""Database persistence layer — core connection, retry, and schema management.

Sub-modules handle specific concerns:
- db_nodes.py    — Node CRUD, queries, tree building, recovery
- db_messages.py — Messaging, mailbox, work queue
- db_stats.py    — Status reports, cost accumulation, hourly stats, restart counts
- db_projects.py — Project labels and JSON sync
"""
import os
import sqlite3
import threading
import time

from .. import constants

_write_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()
_MAX_RETRIES = constants.MAX_RETRIES
_RETRY_BASE_DELAY = constants.RETRY_BASE_DELAY


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
                tmux_session_id TEXT,
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

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_node_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
                to_node_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
                type TEXT NOT NULL DEFAULT 'message',
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                delivered_at TEXT,
                done_at TEXT,
                claimed_by INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
                claim_expires_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_messages_to
                ON messages(to_node_id, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_messages_from
                ON messages(from_node_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_messages_queue
                ON messages(status, created_at)
                WHERE to_node_id IS NULL;
        """)
        conn.commit()
    _migrate()
    from .db_projects import sync_projects_from_json
    sync_projects_from_json()
    from .db_stats import migrate_hourly_stats
    migrate_hourly_stats()


def _migrate():
    conn = _get_conn()
    with _write_lock:
        for col, col_type in [
            ("hidden_at", "TEXT"),
            ("total_tokens_in", "INTEGER DEFAULT 0"),
            ("total_tokens_out", "INTEGER DEFAULT 0"),
            ("total_cost", "REAL DEFAULT 0.0"),
            ("log_count", "INTEGER DEFAULT 0"),
            ("tmux_session_id", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE nodes ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass
    with _write_lock:
        try:
            conn.execute("ALTER TABLE status_reports ADD COLUMN options TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass


# --- Re-exports from sub-modules (preserves public API) ---

from .db_nodes import (  # noqa: E402, F401
    create_node,
    kill_node,
    hide_node,
    reparent_node,
    rename_node,
    update_node_status,
    get_node,
    get_node_by_name,
    get_node_children,
    get_all_nodes,
    get_root_nodes,
    get_nodes_by_project_label_id,
    get_killed_nodes,
    build_tree,
    existing_names,
    active_colours,
    recover_nodes,
    recover_live_nodes,
)

from .db_stats import (  # noqa: E402, F401
    add_status_report,
    prune_all_old_reports,
    vacuum_db,
    get_node_reports,
    accumulate_cost,
    increment_log_count,
    get_restart_count_for_name,
    increment_restart_count,
    snapshot_stats,
    get_hourly_stats,
    get_stats_summary,
)

from .db_projects import (  # noqa: E402, F401
    add_project_label,
    delete_project_label,
    list_project_labels,
    get_project_label_path,
    sync_projects_from_json as _sync_projects_from_json,
)

from .db_messages import (  # noqa: E402, F401
    create_message,
    get_message,
    get_messages_for_node,
    get_pending_messages_for_node,
    mark_message_delivered,
    mark_message_done,
    create_broadcast,
    get_queue_tasks,
    claim_queue_task,
    expire_stale_claims,
)
