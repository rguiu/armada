import sqlite3
import os

DB_DIR = os.path.expanduser("~/.fleet")
DB_PATH = os.path.join(DB_DIR, "fleet.db")


def _ensure_dir():
    os.makedirs(DB_DIR, exist_ok=True)


def _connect() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
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
            killed_at TEXT
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
    conn.close()


# --- Project Labels ---

def add_project_label(id: str, name: str, path: str):
    conn = _connect()
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
    finally:
        conn.close()


def list_project_labels():
    conn = _connect()
    rows = conn.execute("SELECT id, name, path FROM project_labels ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_project_label(id: str):
    conn = _connect()
    conn.execute("DELETE FROM project_labels WHERE id = ?", (id,))
    conn.commit()
    conn.close()


# --- Nodes ---

def create_node(name: str, colour: str, parent_id: int | None = None,
                project_label_id: str | None = None,
                tmux_pane_id: str | None = None,
                agent_type: str = "auto") -> int:
    conn = _connect()
    cursor = conn.execute(
        "INSERT INTO nodes (name, colour, parent_id, project_label_id, tmux_pane_id, agent_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, colour, parent_id, project_label_id, tmux_pane_id, agent_type),
    )
    conn.commit()
    sid = cursor.lastrowid
    conn.close()
    return sid


def kill_node(node_id: int) -> list[dict]:
    """Kill a node and all its descendants. Returns [{id, name}, ...] for tmux cleanup."""
    conn = _connect()
    killed = []
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
    conn.close()
    return killed


def update_node_status(node_id: int, status: str, tmux_pane_id: str | None = None):
    conn = _connect()
    parts = ["status = ?"]
    params = [status]
    if tmux_pane_id is not None:
        parts.append("tmux_pane_id = ?")
        params.append(tmux_pane_id)
    params.append(node_id)
    conn.execute(f"UPDATE nodes SET {', '.join(parts)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def add_status_report(node_id: int, status: str, message: str | None = None):
    conn = _connect()
    conn.execute(
        "INSERT INTO status_reports (node_id, status, message) VALUES (?, ?, ?)",
        (node_id, status, message),
    )
    conn.execute("UPDATE nodes SET status = ? WHERE id = ?", (status, node_id))
    conn.commit()
    conn.close()


def get_node(node_id: int):
    conn = _connect()
    row = conn.execute(
        "SELECT n.*, p.name as project_label_name, p.path as project_path "
        "FROM nodes n LEFT JOIN project_labels p ON n.project_label_id = p.id "
        "WHERE n.id = ?", (node_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_node_by_name(name: str):
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM nodes WHERE name = ? AND killed_at IS NULL", (name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_node_children(node_id: int):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM nodes WHERE parent_id = ? AND killed_at IS NULL", (node_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_nodes():
    """Return all active nodes with their latest status report and project label."""
    conn = _connect()
    rows = conn.execute("""
        SELECT n.id, n.name, n.parent_id, n.project_label_id, n.colour, n.status,
               n.agent_type, n.created_at,
               p.name as project_label_name,
               (SELECT message FROM status_reports WHERE node_id = n.id
                ORDER BY timestamp DESC LIMIT 1) as latest_message,
               (SELECT timestamp FROM status_reports WHERE node_id = n.id
                ORDER BY timestamp DESC LIMIT 1) as latest_report_time
        FROM nodes n
        LEFT JOIN project_labels p ON n.project_label_id = p.id
        WHERE n.killed_at IS NULL
        ORDER BY n.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_node_reports(node_id: int, limit: int = 30):
    conn = _connect()
    rows = conn.execute(
        "SELECT id, node_id, status, message, timestamp FROM status_reports "
        "WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
        (node_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_root_nodes():
    """Return active nodes with no parent."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, name, parent_id, project_label_id, colour, status, created_at "
        "FROM nodes WHERE parent_id IS NULL AND killed_at IS NULL "
        "ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_tree():
    """Build the full node hierarchy as a nested dict."""
    all_nodes = get_all_nodes()
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


def existing_names():
    conn = _connect()
    rows = conn.execute("SELECT name FROM nodes WHERE killed_at IS NULL").fetchall()
    conn.close()
    return {r[0] for r in rows}


def active_colours():
    conn = _connect()
    rows = conn.execute("SELECT colour FROM nodes WHERE killed_at IS NULL").fetchall()
    conn.close()
    return [r[0] for r in rows]
