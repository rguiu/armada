import sqlite3
import os
import json
import threading

DB_DIR = os.path.expanduser("~/.armada")
DB_PATH = os.path.join(DB_DIR, "armada.db")
PROJECTS_FILE = os.path.join(DB_DIR, "projects.json")
_write_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(DB_DIR, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        _ensure_dir()
        _conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA busy_timeout=30000")
        _conn.execute("PRAGMA synchronous=NORMAL")
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


def _execute(fn):
    with _write_lock:
        return fn()


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
        """)
        conn.commit()
    _sync_projects_from_json()
    _migrate_add_hidden_at()
    _migrate_add_cost_columns()
    _migrate_add_log_count()


def _migrate_add_hidden_at():
    conn = _get_conn()
    with _write_lock:
        try:
            conn.execute("ALTER TABLE nodes ADD COLUMN hidden_at TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def _migrate_add_cost_columns():
    conn = _get_conn()
    with _write_lock:
        for col, col_type in [("total_tokens_in", "INTEGER DEFAULT 0"),
                               ("total_tokens_out", "INTEGER DEFAULT 0"),
                               ("total_cost", "REAL DEFAULT 0.0")]:
            try:
                conn.execute(f"ALTER TABLE nodes ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass


def _migrate_add_log_count():
    conn = _get_conn()
    with _write_lock:
        try:
            conn.execute("ALTER TABLE nodes ADD COLUMN log_count INTEGER DEFAULT 0")
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
    _execute(_do)
    _save_projects_to_json()


def delete_project_label(id: str):
    def _do():
        conn = _get_conn()
        conn.execute("DELETE FROM project_labels WHERE id = ?", (id,))
        conn.commit()
    _execute(_do)
    _save_projects_to_json()


def list_project_labels():
    conn = _get_conn()
    rows = conn.execute("SELECT id, name, path FROM project_labels ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_project_label_path(label_id: str) -> str | None:
    conn = _get_conn()
    row = conn.execute("SELECT path FROM project_labels WHERE id = ?", (label_id,)).fetchone()
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
                "INSERT INTO nodes (name, colour, parent_id, project_label_id, tmux_pane_id, agent_type) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, colour, parent_id, project_label_id, tmux_pane_id, agent_type),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE nodes SET killed_at = NULL, hidden_at = NULL, status = 'idle', "
                "colour = ?, parent_id = ?, project_label_id = ?, tmux_pane_id = ?, agent_type = ? "
                "WHERE name = ?",
                (colour, parent_id, project_label_id, tmux_pane_id, agent_type, name),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM nodes WHERE name = ?", (name,)).fetchone()
            return row[0]
    return _execute(_do)


def kill_node(node_id: int) -> list[dict]:
    killed = []
    def _do():
        conn = _get_conn()
        stack = [node_id]
        while stack:
            current = stack.pop()
            children = conn.execute(
                "SELECT id FROM nodes WHERE parent_id = ? AND killed_at IS NULL", (current,)
            ).fetchall()
            for child in children:
                stack.append(child[0])
            name_row = conn.execute("SELECT name FROM nodes WHERE id = ?", (current,)).fetchone()
            killed.append({"id": current, "name": name_row[0] if name_row else ""})
            conn.execute(
                "UPDATE nodes SET killed_at = datetime('now'), status = 'dead' WHERE id = ?",
                (current,),
            )
        conn.commit()
    _execute(_do)
    return killed


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
    _execute(_do)


def add_status_report(node_id: int, status: str, message: str | None = None):
    def _do():
        conn = _get_conn()
        conn.execute(
            "INSERT INTO status_reports (node_id, status, message) VALUES (?, ?, ?)",
            (node_id, status, message),
        )
        conn.execute("UPDATE nodes SET status = ? WHERE id = ?", (status, node_id))
        conn.commit()
    _execute(_do)
    _prune_reports_if_needed(node_id)


_PRUNE_THRESHOLD = 50
_MAX_REPORTS_PER_NODE = 200
_last_prune: dict[int, int] = {}


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
    _execute(_do)


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
    _execute(_do)


def vacuum_db():
    def _do():
        conn = _get_conn()
        conn.execute("PRAGMA optimize")
    _execute(_do)


def accumulate_cost(node_id: int, tokens_in: int = 0, tokens_out: int = 0, cost: float = 0.0):
    def _do():
        conn = _get_conn()
        conn.execute(
            "UPDATE nodes SET total_tokens_in = total_tokens_in + ?, "
            "total_tokens_out = total_tokens_out + ?, "
            "total_cost = total_cost + ? "
            "WHERE id = ?",
            (tokens_in, tokens_out, cost, node_id),
        )
        conn.commit()
    _execute(_do)


def increment_log_count(node_id: int, count: int = 1):
    def _do():
        conn = _get_conn()
        conn.execute(
            "UPDATE nodes SET log_count = log_count + ? WHERE id = ?",
            (count, node_id),
        )
        conn.commit()
    _execute(_do)


def get_node(node_id: int):
    conn = _get_conn()
    row = conn.execute(
        "SELECT n.*, p.name as project_label_name, p.path as project_path "
        "FROM nodes n LEFT JOIN project_labels p ON n.project_label_id = p.id "
        "WHERE n.id = ?", (node_id,)
    ).fetchone()
    return dict(row) if row else None


def get_node_by_name(name: str):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM nodes WHERE name = ? AND killed_at IS NULL AND hidden_at IS NULL", (name,)
    ).fetchone()
    return dict(row) if row else None


def get_node_children(node_id: int):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM nodes WHERE parent_id = ? AND killed_at IS NULL AND hidden_at IS NULL", (node_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_nodes(include_dead: bool = True):
    conn = _get_conn()
    if include_dead:
        rows = conn.execute("""
            SELECT n.id, n.name, n.parent_id, n.project_label_id, n.colour, n.status,
                   n.agent_type, n.created_at, n.killed_at,
                   n.total_tokens_in, n.total_tokens_out, n.total_cost, n.log_count,
                   p.name as project_label_name,
                   (SELECT message FROM status_reports WHERE node_id = n.id
                    ORDER BY timestamp DESC LIMIT 1) as latest_message,
                   (SELECT timestamp FROM status_reports WHERE node_id = n.id
                    ORDER BY timestamp DESC LIMIT 1) as latest_report_time
            FROM nodes n
            LEFT JOIN project_labels p ON n.project_label_id = p.id
            WHERE n.hidden_at IS NULL
            ORDER BY n.created_at DESC
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT n.id, n.name, n.parent_id, n.project_label_id, n.colour, n.status,
                   n.agent_type, n.created_at,
                   n.total_tokens_in, n.total_tokens_out, n.total_cost, n.log_count,
                   p.name as project_label_name,
                   (SELECT message FROM status_reports WHERE node_id = n.id
                    ORDER BY timestamp DESC LIMIT 1) as latest_message,
                   (SELECT timestamp FROM status_reports WHERE node_id = n.id
                    ORDER BY timestamp DESC LIMIT 1) as latest_report_time
            FROM nodes n
            LEFT JOIN project_labels p ON n.project_label_id = p.id
            WHERE n.killed_at IS NULL AND n.hidden_at IS NULL
            ORDER BY n.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def get_node_reports(node_id: int, limit: int = 30):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, node_id, status, message, timestamp FROM status_reports "
        "WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
        (node_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_root_nodes():
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, parent_id, project_label_id, colour, status, created_at "
        "FROM nodes WHERE parent_id IS NULL AND killed_at IS NULL AND hidden_at IS NULL "
        "ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def build_tree(include_dead: bool = True):
    all_nodes = get_all_nodes(include_dead=include_dead)
    node_map = {}
    for n in all_nodes:
        n["children"] = []
        node_map[n["id"]] = n

    roots = []
    for n in all_nodes:
        if n["parent_id"] and n["parent_id"] in node_map:
            node_map[n["parent_id"]]["children"].append(n)
        else:
            roots.append(n)

    return roots


def get_killed_nodes(limit: int = 50):
    conn = _get_conn()
    rows = conn.execute("""
        SELECT n.id, n.name, n.colour, n.agent_type, n.status,
               n.created_at, n.killed_at, n.project_label_id,
               p.name as project_label_name,
               (SELECT message FROM status_reports WHERE node_id = n.id
                ORDER BY timestamp DESC LIMIT 1) as latest_message
        FROM nodes n
        LEFT JOIN project_labels p ON n.project_label_id = p.id
        WHERE n.killed_at IS NOT NULL AND n.hidden_at IS NULL
        ORDER BY n.killed_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def hide_node(node_id: int) -> list[dict]:
    hidden = []
    def _do():
        conn = _get_conn()
        stack = [node_id]
        while stack:
            current = stack.pop()
            children = conn.execute(
                "SELECT id FROM nodes WHERE parent_id = ? AND hidden_at IS NULL", (current,)
            ).fetchall()
            for child in children:
                stack.append(child[0])
            name_row = conn.execute("SELECT name FROM nodes WHERE id = ?", (current,)).fetchone()
            hidden.append({"id": current, "name": name_row[0] if name_row else ""})
            conn.execute(
                "UPDATE nodes SET hidden_at = datetime('now'), status = 'dead' WHERE id = ?",
                (current,),
            )
        conn.commit()
    _execute(_do)
    return hidden


def reparent_node(node_id: int, parent_id: int | None):
    def _do():
        conn = _get_conn()
        conn.execute(
            "UPDATE nodes SET parent_id = ? WHERE id = ?",
            (parent_id, node_id),
        )
        conn.commit()
    _execute(_do)


def rename_node(node_id: int, new_name: str):
    def _do():
        conn = _get_conn()
        conn.execute(
            "UPDATE nodes SET name = ? WHERE id = ?",
            (new_name, node_id),
        )
        conn.commit()
    _execute(_do)


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
    _execute(_do)


def recover_live_nodes(running_names: set[str]) -> list[dict]:
    if not running_names:
        return []
    conn = _get_conn()
    placeholders = ",".join("?" * len(running_names))
    rows = conn.execute(
        f"SELECT id, name, colour, parent_id, project_label_id, tmux_pane_id, agent_type "
        f"FROM nodes WHERE killed_at IS NULL AND hidden_at IS NULL AND name IN ({placeholders})",
        list(running_names),
    ).fetchall()
    return [dict(r) for r in rows]


def existing_names():
    conn = _get_conn()
    rows = conn.execute("SELECT name FROM nodes WHERE hidden_at IS NULL").fetchall()
    return {r[0] for r in rows}


def active_colours():
    conn = _get_conn()
    rows = conn.execute("SELECT colour FROM nodes WHERE killed_at IS NULL AND hidden_at IS NULL").fetchall()
    return [r[0] for r in rows]


# --- Projects JSON persistence ---

def _save_projects_to_json():
    projects = list_project_labels()
    _ensure_dir()
    with open(PROJECTS_FILE, "w") as f:
        json.dump(projects, f, indent=2)


def _sync_projects_from_json():
    if not os.path.exists(PROJECTS_FILE):
        _save_projects_to_json()
        return

    try:
        with open(PROJECTS_FILE) as f:
            json_projects = json.load(f)
    except (json.JSONDecodeError, IOError):
        _save_projects_to_json()
        return

    db_projects = {p["id"]: p for p in list_project_labels()}

    for jp in json_projects:
        if jp["id"] not in db_projects:
            add_project_label(jp["id"], jp["name"], jp["path"])
            continue
        db_p = db_projects[jp["id"]]
        if jp["name"] != db_p["name"] or jp["path"] != db_p["path"]:
            add_project_label(jp["id"], jp["name"], jp["path"])
            continue

    db_ids = {p["id"] for p in db_projects.values()}
    json_ids = {p["id"] for p in json_projects if isinstance(p, dict)}
    if db_ids != json_ids:
        _save_projects_to_json()
