"""Message/mailbox/queue persistence."""
from ..domain.models import Message
from .database import _get_conn, _retry


_MSG_SELECT = """
    SELECT m.*,
           fn.name AS from_node_name,
           tn.name AS to_node_name
    FROM messages m
    LEFT JOIN nodes fn ON fn.id = m.from_node_id
    LEFT JOIN nodes tn ON tn.id = m.to_node_id
"""


def create_message(
    from_node_id: int | None,
    to_node_id: int | None,
    msg_type: str = "message",
    payload: str = "{}",
) -> int:
    def _do():
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO messages (from_node_id, to_node_id, type, payload) VALUES (?, ?, ?, ?)",
            (from_node_id, to_node_id, msg_type, payload),
        )
        conn.commit()
        return cur.lastrowid
    return _retry(_do, write=True)


def get_message(message_id: int) -> Message | None:
    def _do():
        row = _get_conn().execute(
            _MSG_SELECT + " WHERE m.id = ?", (message_id,)
        ).fetchone()
        return Message.from_row(dict(row)) if row else None
    return _retry(_do)


def get_messages_for_node(
    node_id: int, status: str | None = None, limit: int = 50
) -> list[Message]:
    def _do():
        if status and status != "all":
            rows = _get_conn().execute(
                _MSG_SELECT + " WHERE m.to_node_id = ? AND m.status = ? ORDER BY m.created_at DESC LIMIT ?",
                (node_id, status, limit),
            ).fetchall()
        else:
            rows = _get_conn().execute(
                _MSG_SELECT + " WHERE m.to_node_id = ? ORDER BY m.created_at DESC LIMIT ?",
                (node_id, limit),
            ).fetchall()
        return [Message.from_row(dict(r)) for r in rows]
    return _retry(_do)


def get_pending_messages_for_node(node_id: int) -> list[Message]:
    return get_messages_for_node(node_id, status="pending")


def mark_message_delivered(message_id: int) -> bool:
    def _do():
        conn = _get_conn()
        conn.execute(
            "UPDATE messages SET status = 'delivered', delivered_at = datetime('now') WHERE id = ? AND status = 'pending'",
            (message_id,),
        )
        conn.commit()
        return True
    return _retry(_do, write=True)


def mark_message_done(message_id: int) -> bool:
    def _do():
        conn = _get_conn()
        cur = conn.execute(
            "UPDATE messages SET status = 'done', done_at = datetime('now') WHERE id = ? AND status IN ('pending', 'delivered', 'claimed')",
            (message_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    return _retry(_do, write=True)


def create_broadcast(
    from_node_id: int, msg_type: str, payload: str
) -> list[int]:
    def _do():
        conn = _get_conn()
        children = conn.execute(
            "SELECT id FROM nodes WHERE parent_id = ? AND killed_at IS NULL AND hidden_at IS NULL",
            (from_node_id,),
        ).fetchall()
        ids = []
        for child in children:
            cur = conn.execute(
                "INSERT INTO messages (from_node_id, to_node_id, type, payload) VALUES (?, ?, ?, ?)",
                (from_node_id, child["id"], msg_type, payload),
            )
            ids.append(cur.lastrowid)
        conn.commit()
        return ids
    return _retry(_do, write=True)


def get_queue_tasks(
    status: str = "pending", limit: int = 50
) -> list[Message]:
    def _do():
        rows = _get_conn().execute(
            _MSG_SELECT + " WHERE m.to_node_id IS NULL AND m.status = ? ORDER BY m.created_at ASC LIMIT ?",
            (status, limit),
        ).fetchall()
        return [Message.from_row(dict(r)) for r in rows]
    return _retry(_do)


def claim_queue_task(
    message_id: int, claimer_node_id: int, expires_minutes: int = 10
) -> bool:
    def _do():
        conn = _get_conn()
        cur = conn.execute(
            """UPDATE messages
               SET status = 'claimed',
                   claimed_by = ?,
                   delivered_at = datetime('now'),
                   claim_expires_at = datetime('now', '+' || ? || ' minutes')
               WHERE id = ? AND status = 'pending' AND to_node_id IS NULL""",
            (claimer_node_id, expires_minutes, message_id),
        )
        conn.commit()
        return cur.rowcount > 0
    return _retry(_do, write=True)


def expire_stale_claims() -> int:
    def _do():
        conn = _get_conn()
        cur = conn.execute(
            """UPDATE messages
               SET status = 'pending', claimed_by = NULL, delivered_at = NULL, claim_expires_at = NULL
               WHERE status = 'claimed' AND claim_expires_at < datetime('now')""",
        )
        conn.commit()
        return cur.rowcount
    return _retry(_do, write=True)
