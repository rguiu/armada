"""Node CRUD operations and tree queries."""
import sqlite3

from ..domain.models import Node
from .database import _get_conn, _retry


def create_node(name: str, colour: str, parent_id: int | None = None,
                project_label_id: str | None = None,
                tmux_pane_id: str | None = None,
                tmux_session_id: str | None = None,
                agent_type: str = "auto") -> int:
    def _do():
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "INSERT INTO nodes (name, colour, parent_id, project_label_id, "
                "tmux_pane_id, tmux_session_id, agent_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, colour, parent_id, project_label_id, tmux_pane_id,
                 tmux_session_id, agent_type),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE nodes SET killed_at = NULL, hidden_at = NULL, status = 'idle', "
                "colour = ?, parent_id = ?, project_label_id = ?, tmux_pane_id = ?, "
                "tmux_session_id = ?, agent_type = ? WHERE name = ?",
                (colour, parent_id, project_label_id, tmux_pane_id,
                 tmux_session_id, agent_type, name),
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
        killed.clear()
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
        hidden.clear()
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


def update_node_status(node_id: int, status: str, tmux_pane_id: str | None = None,
                       tmux_session_id: str | None = None):
    def _do():
        conn = _get_conn()
        parts = ["status = ?"]
        params = [status]
        if status != "dead":
            parts.append("killed_at = NULL")
        if tmux_pane_id is not None:
            parts.append("tmux_pane_id = ?")
            params.append(tmux_pane_id)
        if tmux_session_id is not None:
            parts.append("tmux_session_id = ?")
            params.append(tmux_session_id)
        params.append(node_id)
        conn.execute(f"UPDATE nodes SET {', '.join(parts)} WHERE id = ?", params)
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
               n.agent_type, n.created_at, {} n.tmux_pane_id,
               n.tmux_session_id,
               n.total_tokens_in, n.total_tokens_out,
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
        f"SELECT id, name, colour, parent_id, project_label_id, tmux_pane_id, "
        f"tmux_session_id, agent_type "
        f"FROM nodes WHERE killed_at IS NULL AND hidden_at IS NULL AND name IN ({placeholders})",
        list(running_names),
    ).fetchall()
    return [Node.from_row(dict(r)) for r in rows]
