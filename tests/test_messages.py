"""Tests for message delivery, auth manager, and concurrent DB access."""

import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from armada_ai.infrastructure.auth_manager import TokenManager, AuthExemptPaths


def _mkproj(temp_db, id="proj", name="Project"):
    path = tempfile.mkdtemp(prefix=f"armada_test_{id}_")
    temp_db.add_project_label(id, name, path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Part 1: Message delivery tests
# ─────────────────────────────────────────────────────────────────────────────


class TestMessageDelivery:
    """Test _deliver_pending_messages from server.py."""

    def test_deliver_to_alive_node(self, temp_db):
        """Deliver a pending message to a live node."""
        import sys
        tmux = sys.modules["armada_ai.tmux"]

        nid = temp_db.create_node("sender", "#111")
        rid = temp_db.create_node("receiver", "#222")
        temp_db.create_message(nid, rid, "task", "do something")

        from armada_ai.server import _deliver_pending_messages
        node = temp_db.get_node(rid)
        delivered = _deliver_pending_messages(node)
        assert delivered == 1
        tmux.send_keys.assert_called()

    def test_deliver_marks_message_delivered(self, temp_db):
        """After delivery, message status should be 'delivered'."""
        import sys
        sys.modules["armada_ai.tmux"]

        nid = temp_db.create_node("s", "#111")
        rid = temp_db.create_node("r", "#222")
        msg_id = temp_db.create_message(nid, rid, "task", "hello")

        from armada_ai.server import _deliver_pending_messages
        node = temp_db.get_node(rid)
        _deliver_pending_messages(node)

        msg = temp_db.get_message(msg_id)
        assert msg.status == "delivered"

    def test_deliver_skips_dead_node(self, temp_db):
        """Should not deliver to dead nodes."""
        import sys
        tmux = sys.modules["armada_ai.tmux"]
        tmux.send_keys.reset_mock()

        nid = temp_db.create_node("s2", "#111")
        rid = temp_db.create_node("r2", "#222")
        temp_db.kill_node(rid)
        temp_db.create_message(nid, rid, "task", "hello")

        from armada_ai.server import _deliver_pending_messages
        node = temp_db.get_node(rid)
        delivered = _deliver_pending_messages(node)
        assert delivered == 0

    def test_deliver_no_pending(self, temp_db):
        """No messages means nothing delivered."""
        rid = temp_db.create_node("lonely", "#222")

        from armada_ai.server import _deliver_pending_messages
        node = temp_db.get_node(rid)
        delivered = _deliver_pending_messages(node)
        assert delivered == 0


class TestMessageAPI:
    """Test message endpoints via the FastAPI test client."""

    def test_create_message(self, temp_db, client):
        """POST /api/nodes/{id}/messages creates a message."""
        sid = temp_db.create_node("api-sender", "#111")
        rid = temp_db.create_node("api-recv", "#222")
        # Set receiver to active so auto-delivery doesn't trigger
        temp_db.update_node_status(rid, "active")

        r = client.post(f"/api/nodes/{rid}/messages", json={
            "from_node_id": sid,
            "type": "task",
            "payload": "do the thing",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["to_node_id"] == rid
        assert data["from_node_id"] == sid
        assert data["status"] == "pending"

    def test_get_messages_for_node(self, temp_db, client):
        """GET /api/nodes/{id}/messages returns inbox."""
        sid = temp_db.create_node("inbox-s", "#111")
        rid = temp_db.create_node("inbox-r", "#222")
        temp_db.create_message(sid, rid, "task", "msg1")
        temp_db.create_message(sid, rid, "task", "msg2")

        r = client.get(f"/api/nodes/{rid}/messages?status=pending")
        assert r.status_code == 200
        msgs = r.json()
        assert len(msgs) == 2

    def test_ack_message(self, temp_db, client):
        """PATCH /api/messages/{id} with status=done marks it done."""
        sid = temp_db.create_node("ack-s", "#111")
        rid = temp_db.create_node("ack-r", "#222")
        msg_id = temp_db.create_message(sid, rid, "task", "ack me")

        r = client.patch(f"/api/messages/{msg_id}", json={"status": "done"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        msg = temp_db.get_message(msg_id)
        assert msg.status == "done"

    def test_broadcast_to_children(self, temp_db, client):
        """POST /api/nodes/{id}/broadcast creates messages for all children."""
        _mkproj(temp_db, "bcast", "Broadcast")
        parent_id = temp_db.create_node("parent", "#111", project_label_id="bcast")
        temp_db.create_node("child1", "#222", parent_id=parent_id, project_label_id="bcast")
        temp_db.create_node("child2", "#333", parent_id=parent_id, project_label_id="bcast")

        r = client.post(f"/api/nodes/{parent_id}/broadcast", json={
            "type": "instruction",
            "payload": "everybody do this",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["messages_created"] == 2
        assert len(data["message_ids"]) == 2

    def test_broadcast_no_children(self, temp_db, client):
        """Broadcast with no children creates zero messages."""
        nid = temp_db.create_node("solo", "#111")
        r = client.post(f"/api/nodes/{nid}/broadcast", json={
            "type": "msg",
            "payload": "echo",
        })
        assert r.status_code == 201
        assert r.json()["messages_created"] == 0

    def test_queue_post_and_claim(self, temp_db, client):
        """POST /api/queue then claim via POST /api/queue/{id}/claim."""
        worker_id = temp_db.create_node("worker", "#111")

        r = client.post("/api/queue", json={
            "from_node_id": worker_id,
            "payload": "build artifact",
        })
        assert r.status_code == 201
        task_id = r.json()["id"]
        assert r.json()["status"] == "pending"

        r2 = client.post(f"/api/queue/{task_id}/claim", json={
            "node_id": worker_id,
            "expires_minutes": 5,
        })
        assert r2.status_code == 200
        assert r2.json()["status"] == "claimed"
        assert r2.json()["claimed_by"] == worker_id

    def test_queue_double_claim_fails(self, temp_db, client):
        """Claiming an already-claimed task returns 409."""
        w1 = temp_db.create_node("w1", "#111")
        w2 = temp_db.create_node("w2", "#222")

        r = client.post("/api/queue", json={"payload": "single task"})
        task_id = r.json()["id"]

        client.post(f"/api/queue/{task_id}/claim", json={"node_id": w1})
        r2 = client.post(f"/api/queue/{task_id}/claim", json={"node_id": w2})
        assert r2.status_code == 409

    def test_queue_expire_stale_claims(self, temp_db, client):
        """Expired claims get reset to pending."""
        wid = temp_db.create_node("expirer", "#111")

        msg_id = temp_db.create_message(None, None, "task", "expire me")
        # Claim with very short expiry
        temp_db.claim_queue_task(msg_id, wid, expires_minutes=0)

        # Force expiry by backdating claim_expires_at
        from armada_ai.infrastructure.database import _get_conn
        conn = _get_conn()
        conn.execute(
            "UPDATE messages SET claim_expires_at = datetime('now', '-1 minute') WHERE id = ?",
            (msg_id,),
        )
        conn.commit()

        expired = temp_db.expire_stale_claims()
        assert expired >= 1

        msg = temp_db.get_message(msg_id)
        assert msg.status == "pending"
        assert msg.claimed_by is None

    def test_get_messages_nonexistent_node(self, temp_db, client):
        """GET messages for a node that doesn't exist returns 404."""
        r = client.get("/api/nodes/9999/messages")
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Part 2: Auth manager tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTokenManager:
    """Test TokenManager lifecycle and validation."""

    def test_creates_token_file(self):
        """ensure() creates a token file if none exists."""
        tmpdir = tempfile.mkdtemp()
        path = f"{tmpdir}/armada_token"
        tm = TokenManager(path)
        token = tm.ensure(keep=False)
        assert token
        assert len(token) == 32  # hex(16) = 32 chars
        with open(path) as f:
            assert f.read().strip() == token

    def test_get_token_returns_current(self):
        """After ensure, token property returns the current value."""
        tmpdir = tempfile.mkdtemp()
        path = f"{tmpdir}/tok"
        tm = TokenManager(path)
        token = tm.ensure()
        assert tm.token == token

    def test_validate_correct_token(self):
        """validate() returns True for the correct token."""
        tmpdir = tempfile.mkdtemp()
        tm = TokenManager(f"{tmpdir}/tok")
        token = tm.ensure()
        assert tm.validate(token) is True

    def test_validate_wrong_token(self):
        """validate() returns False for a wrong token."""
        tmpdir = tempfile.mkdtemp()
        tm = TokenManager(f"{tmpdir}/tok")
        tm.ensure()
        assert tm.validate("wrong-token") is False

    def test_validate_empty_not_set(self):
        """validate() returns False when no token has been set."""
        tmpdir = tempfile.mkdtemp()
        tm = TokenManager(f"{tmpdir}/tok")
        assert tm.validate("anything") is False

    def test_ensure_keep_true_preserves_token(self):
        """ensure(keep=True) does not rotate an existing token."""
        tmpdir = tempfile.mkdtemp()
        path = f"{tmpdir}/tok"
        tm = TokenManager(path)
        first = tm.ensure(keep=True)
        # Create a new instance to simulate restart
        tm2 = TokenManager(path)
        second = tm2.ensure(keep=True)
        assert first == second

    def test_ensure_keep_false_rotates_token(self):
        """ensure(keep=False) generates a new token each time."""
        tmpdir = tempfile.mkdtemp()
        path = f"{tmpdir}/tok"
        # Write an initial token
        with open(path, "w") as f:
            f.write("old-token-value")
        tm = TokenManager(path)
        token = tm.ensure(keep=False)
        # Should NOT be the old value (it generates fresh)
        assert token != "old-token-value"
        assert len(token) == 32


class TestAuthExemptPaths:
    """Test which paths are exempt from auth."""

    def test_health_is_exempt(self):
        assert AuthExemptPaths.is_exempt("/health") is True

    def test_manifest_is_exempt(self):
        assert AuthExemptPaths.is_exempt("/manifest.json") is True

    def test_metrics_is_exempt(self):
        assert AuthExemptPaths.is_exempt("/metrics") is True

    def test_api_nodes_not_exempt(self):
        assert AuthExemptPaths.is_exempt("/api/nodes") is False

    def test_api_tree_not_exempt(self):
        assert AuthExemptPaths.is_exempt("/api/tree") is False

    def test_report_is_exempt(self):
        assert AuthExemptPaths.is_exempt("/api/report") is True


# ─────────────────────────────────────────────────────────────────────────────
# Part 3: Concurrent DB tests
# ─────────────────────────────────────────────────────────────────────────────


class TestConcurrentDB:
    """Exercise the database under concurrent access.

    Uses raw sqlite3 connections (one per thread) to the same WAL-mode
    database, which avoids segfaults from sharing a single Python sqlite3
    connection object across threads.
    """

    def _init_db(self):
        """Create a fresh WAL-mode SQLite database and return its path."""
        import sqlite3
        tmpdir = tempfile.mkdtemp(prefix="armada_conc_")
        db_path = f"{tmpdir}/conc.db"
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.executescript("""
            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                parent_id INTEGER,
                colour TEXT NOT NULL,
                status TEXT DEFAULT 'idle',
                agent_type TEXT DEFAULT 'auto',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                killed_at TEXT,
                hidden_at TEXT
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_node_id INTEGER,
                to_node_id INTEGER,
                type TEXT NOT NULL DEFAULT 'message',
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                delivered_at TEXT,
                done_at TEXT,
                claimed_by INTEGER,
                claim_expires_at TEXT
            );
        """)
        conn.commit()
        conn.close()
        return db_path

    def _connect(self, db_path):
        import sqlite3
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    def test_concurrent_node_creation(self):
        """5 threads creating nodes simultaneously — all succeed, no duplicates."""
        db_path = self._init_db()
        results = []
        errors = []
        lock = threading.Lock()

        def do_create(i):
            try:
                conn = self._connect(db_path)
                cur = conn.execute(
                    "INSERT INTO nodes (name, colour) VALUES (?, ?)",
                    (f"conc-{i}", f"#{i:03d}"),
                )
                conn.commit()
                with lock:
                    results.append(cur.lastrowid)
                conn.close()
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=do_create, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 5
        assert len(set(results)) == 5

        # Verify all nodes exist
        conn = self._connect(db_path)
        rows = conn.execute("SELECT name FROM nodes").fetchall()
        names = {r["name"] for r in rows}
        conn.close()
        for i in range(5):
            assert f"conc-{i}" in names

    def test_concurrent_kill_same_node(self):
        """3 threads killing the same node — only one succeeds, no errors."""
        db_path = self._init_db()
        conn = self._connect(db_path)
        conn.execute("INSERT INTO nodes (name, colour) VALUES ('target', '#FFF')")
        conn.commit()
        nid = conn.execute("SELECT id FROM nodes WHERE name='target'").fetchone()["id"]
        conn.close()

        kill_counts = []
        errors = []
        lock = threading.Lock()

        def do_kill(_):
            try:
                c = self._connect(db_path)
                cur = c.execute(
                    "UPDATE nodes SET killed_at = datetime('now'), status = 'dead' "
                    "WHERE id = ? AND killed_at IS NULL",
                    (nid,),
                )
                c.commit()
                with lock:
                    kill_counts.append(cur.rowcount)
                c.close()
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=do_kill, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors: {errors}"
        # Exactly one thread should have rowcount == 1
        assert sum(kill_counts) == 1
        # Node should be dead
        conn = self._connect(db_path)
        row = conn.execute("SELECT killed_at FROM nodes WHERE id=?", (nid,)).fetchone()
        conn.close()
        assert row["killed_at"] is not None

    def test_concurrent_write_read_contention(self):
        """Writers don't block readers for long (WAL mode)."""
        db_path = self._init_db()
        # Seed some nodes
        conn = self._connect(db_path)
        for i in range(3):
            conn.execute("INSERT INTO nodes (name, colour) VALUES (?, ?)",
                         (f"rw-{i}", f"#{i:03d}"))
        conn.commit()
        conn.close()

        read_times = []
        write_errors = []
        lock = threading.Lock()

        def writer(n):
            try:
                c = self._connect(db_path)
                for j in range(10):
                    c.execute(
                        "INSERT INTO messages (type, payload, status) VALUES ('task', ?, 'pending')",
                        (f"work-{n}-{j}",),
                    )
                    c.commit()
                c.close()
            except Exception as e:
                with lock:
                    write_errors.append(e)

        def reader():
            c = self._connect(db_path)
            start = time.time()
            for _ in range(20):
                c.execute("SELECT * FROM nodes").fetchall()
            elapsed = time.time() - start
            c.close()
            with lock:
                read_times.append(elapsed)

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = []
            for n in range(3):
                futures.append(pool.submit(writer, n))
            for _ in range(3):
                futures.append(pool.submit(reader))
            for f in as_completed(futures):
                f.result()

        assert len(write_errors) == 0, f"Write errors: {write_errors}"
        for rt in read_times:
            assert rt < 5.0, f"Reader took too long: {rt:.2f}s"

    def test_concurrent_message_creation(self):
        """Multiple threads creating messages don't lose any."""
        db_path = self._init_db()
        conn = self._connect(db_path)
        conn.execute("INSERT INTO nodes (name, colour) VALUES ('target', '#AAA')")
        conn.commit()
        nid = conn.execute("SELECT id FROM nodes WHERE name='target'").fetchone()["id"]
        conn.close()

        msg_count = 20

        def create_msgs(offset):
            c = self._connect(db_path)
            for i in range(msg_count):
                c.execute(
                    "INSERT INTO messages (from_node_id, to_node_id, type, payload, status) "
                    "VALUES (NULL, ?, 'task', ?, 'pending')",
                    (nid, f"msg-{offset}-{i}"),
                )
                c.commit()
            c.close()

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(create_msgs, offset) for offset in range(4)]
            for f in as_completed(futures):
                f.result()

        conn = self._connect(db_path)
        rows = conn.execute(
            "SELECT * FROM messages WHERE to_node_id = ?", (nid,)
        ).fetchall()
        conn.close()
        assert len(rows) == msg_count * 4
