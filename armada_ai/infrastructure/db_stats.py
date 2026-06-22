"""Stats, cost accumulation, status reports, and restart counts."""
from .database import _get_conn, _retry, _write_lock


# --- Restart counts (in-memory, not persisted to DB) ---

_restart_counts: dict[str, int] = {}


def get_restart_count_for_name(name: str) -> int:
    return _restart_counts.get(name, 0)


def increment_restart_count(name: str):
    _restart_counts[name] = _restart_counts.get(name, 0) + 1


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


def get_node_reports(node_id: int, limit: int = 30) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, node_id, status, message, options, timestamp FROM status_reports "
        "WHERE node_id = ? ORDER BY id DESC LIMIT ?",
        (node_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


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


# --- Hourly Stats ---

def migrate_hourly_stats():
    import sqlite3
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
    from .db_nodes import get_all_nodes

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
    from .db_nodes import get_all_nodes

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
