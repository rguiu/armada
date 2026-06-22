"""Tests for health loop, auto-restart, and recovery logic in armada_ai/server.py."""
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import armada_ai.server as server_mod
import armada_ai.constants as constants
from armada_ai.infrastructure.database import _get_conn

# The tmux mock lives in sys.modules, injected by conftest
_tmux = sys.modules["armada_ai.tmux"]


class _DefaultNodeWindowResult:
    pane_id = "%0"
    session_id = "armada-test"
    error = None
    @property
    def ok(self):
        return True


@pytest.fixture(autouse=True)
def _reset_tmux_mock():
    """Reset tmux mock to conftest defaults after each test."""
    yield
    _tmux.pane_alive.return_value = True
    _tmux.pane_alive.side_effect = None
    _tmux.window_exists.return_value = True
    _tmux.window_exists.side_effect = None
    _tmux.capture_pane_content.return_value = ""
    _tmux.capture_pane_content.side_effect = None
    _tmux.kill_node_window.return_value = None
    _tmux.kill_node_window.side_effect = None
    _tmux.create_node_window.side_effect = None
    _tmux.create_node_window.return_value = _DefaultNodeWindowResult()
    _tmux.send_keys.return_value = True


def _create_test_node(temp_db, name="alpha", pane_id="%1", status="idle"):
    """Helper: create a project label + node in the test DB, return node id."""
    path = tempfile.mkdtemp()
    try:
        temp_db.add_project_label("proj", "Project", path)
    except (ValueError, Exception):
        pass  # already exists from a previous call in the same test

    node_id = temp_db.create_node(
        name=name,
        colour="#ff0000",
        parent_id=None,
        project_label_id="proj",
        tmux_pane_id=pane_id,
        tmux_session_id="armada-test",
        agent_type="auto",
    )
    if status != "idle":
        temp_db.update_node_status(node_id, status)
    return node_id


def _make_node_old(temp_db, node_id, seconds_ago=30):
    """Set the node's created_at to the given seconds in the past."""
    old_time = (datetime.now() - timedelta(seconds=seconds_ago)).isoformat()
    conn = _get_conn()
    conn.execute("UPDATE nodes SET created_at = ? WHERE id = ?", (old_time, node_id))
    conn.commit()


# --- _run_health_check ---


class TestRunHealthCheck:
    """Tests for the main _run_health_check function."""

    def test_marks_node_dead_when_pane_gone(self, temp_db):
        """Node is marked dead when tmux pane is not alive and window does not exist.

        We disable auto-restart to test the mark-dead logic in isolation.
        """
        node_id = _create_test_node(temp_db, name="node-dead-pane", pane_id="%10")
        _make_node_old(temp_db, node_id)

        _tmux.pane_alive.return_value = False
        _tmux.window_exists.return_value = False
        _tmux.capture_pane_content.return_value = "some output"
        _tmux.kill_node_window.return_value = None

        # Patch auto-restart to a no-op so we can verify _mark_node_dead ran
        with patch.object(server_mod, "_auto_restart_node"):
            server_mod._run_health_check()

        node = temp_db.get_node(node_id)
        assert node.status == "dead"

    def test_auto_restarts_dead_node(self, temp_db):
        """Health check triggers auto-restart after marking a node dead,
        resulting in an active node with the same name."""
        node_id = _create_test_node(temp_db, name="node-restarted", pane_id="%10b")
        _make_node_old(temp_db, node_id)

        _tmux.pane_alive.return_value = False
        _tmux.window_exists.return_value = False
        _tmux.capture_pane_content.return_value = ""
        _tmux.kill_node_window.return_value = None

        fake_result = MagicMock()
        fake_result.pane_id = "%99"
        fake_result.session_id = "armada-test"
        _tmux.create_node_window.return_value = fake_result

        from armada_ai.infrastructure.db_stats import _restart_counts
        _restart_counts.pop("node-restarted", None)
        server_mod._restarting_nodes.discard("node-restarted")

        server_mod._run_health_check()

        # After auto-restart, the node should be active again
        node = temp_db.get_node_by_name("node-restarted")
        assert node is not None
        assert node.status == "active"

    def test_skips_node_with_live_pane(self, temp_db):
        """Node with a live pane is NOT marked dead."""
        node_id = _create_test_node(temp_db, name="node-alive", pane_id="%11")

        _tmux.pane_alive.return_value = True

        server_mod._run_health_check()

        node = temp_db.get_node(node_id)
        assert node.status != "dead"

    def test_skips_node_without_pane_id_if_window_exists(self, temp_db):
        """Node without a tmux_pane_id is skipped if its named window exists."""
        node_id = _create_test_node(temp_db, name="node-no-pane", pane_id=None)

        _tmux.pane_alive.return_value = False
        _tmux.window_exists.return_value = True

        server_mod._run_health_check()

        node = temp_db.get_node(node_id)
        assert node.status != "dead"

    def test_skips_recently_created_node(self, temp_db):
        """Nodes created less than 15 seconds ago are not killed."""
        node_id = _create_test_node(temp_db, name="node-young", pane_id="%12")

        _tmux.pane_alive.return_value = False
        _tmux.window_exists.return_value = False

        # The node was just created so created_at is < 15s ago
        server_mod._run_health_check()

        node = temp_db.get_node(node_id)
        assert node.status != "dead"

    def test_kills_old_node_with_dead_pane(self, temp_db):
        """Node older than 15s with dead pane is marked dead (auto-restart disabled)."""
        node_id = _create_test_node(temp_db, name="node-old", pane_id="%13")
        _make_node_old(temp_db, node_id)

        _tmux.pane_alive.return_value = False
        _tmux.window_exists.return_value = False
        _tmux.capture_pane_content.return_value = ""
        _tmux.kill_node_window.return_value = None

        with patch.object(server_mod, "_auto_restart_node"):
            server_mod._run_health_check()

        node = temp_db.get_node(node_id)
        assert node.status == "dead"


# --- _mark_node_dead ---


class TestMarkNodeDead:
    """Tests for _mark_node_dead."""

    def test_kills_node_in_db_and_tmux(self, temp_db):
        """Marks the node dead in DB, captures pane content, kills tmux window."""
        node_id = _create_test_node(temp_db, name="mark-dead-1", pane_id="%20")

        _tmux.capture_pane_content.return_value = "final output"
        _tmux.kill_node_window.return_value = None

        server_mod._mark_node_dead(node_id)

        node = temp_db.get_node(node_id)
        assert node.status == "dead"
        _tmux.capture_pane_content.assert_called_with("mark-dead-1")
        _tmux.kill_node_window.assert_called_with("mark-dead-1")

    def test_handles_capture_exception(self, temp_db):
        """Does not raise if capture_pane_content throws."""
        node_id = _create_test_node(temp_db, name="mark-dead-2", pane_id="%21")

        _tmux.capture_pane_content.side_effect = RuntimeError("tmux gone")
        _tmux.kill_node_window.return_value = None

        # Should not raise
        server_mod._mark_node_dead(node_id)

        node = temp_db.get_node(node_id)
        assert node.status == "dead"

        # Reset side_effect for other tests
        _tmux.capture_pane_content.side_effect = None


# --- _auto_restart_node ---


class TestAutoRestartNode:
    """Tests for _auto_restart_node."""

    def setup_method(self):
        # Clear restarting nodes set between tests
        server_mod._restarting_nodes.clear()

    def test_creates_new_node_on_restart(self, temp_db):
        """Auto-restart creates a new tmux window and DB node."""
        node_id = _create_test_node(temp_db, name="restart-node", pane_id="%30")
        node = temp_db.get_node(node_id)

        # Reset restart count for this node name
        from armada_ai.infrastructure.db_stats import _restart_counts
        _restart_counts.pop("restart-node", None)

        fake_result = MagicMock()
        fake_result.pane_id = "%31"
        fake_result.session_id = "armada-test"
        _tmux.create_node_window.return_value = fake_result

        server_mod._auto_restart_node(node)

        _tmux.create_node_window.assert_called_with(
            name="restart-node",
            colour=node.colour,
            working_dir=temp_db.get_project_label_path(node.project_label_id),
            agent_type=node.agent_type,
        )

        # A new node with the same name should exist (reused via IntegrityError path)
        new_node = temp_db.get_node_by_name("restart-node")
        assert new_node is not None

    def test_respects_max_restarts_limit(self, temp_db):
        """Does not restart once MAX_RESTARTS is reached."""
        node_id = _create_test_node(temp_db, name="maxed-out", pane_id="%32")
        node = temp_db.get_node(node_id)

        # Set restart count to MAX_RESTARTS
        from armada_ai.infrastructure.db_stats import _restart_counts
        _restart_counts["maxed-out"] = constants.MAX_RESTARTS

        _tmux.create_node_window.reset_mock()

        server_mod._auto_restart_node(node)

        _tmux.create_node_window.assert_not_called()

        # Cleanup
        _restart_counts.pop("maxed-out", None)

    def test_prevents_concurrent_double_restart(self, temp_db):
        """If a node is already in _restarting_nodes, the restart is skipped."""
        node_id = _create_test_node(temp_db, name="double-restart", pane_id="%33")
        node = temp_db.get_node(node_id)

        # Simulate another thread already restarting this node
        server_mod._restarting_nodes.add("double-restart")

        _tmux.create_node_window.reset_mock()

        server_mod._auto_restart_node(node)

        _tmux.create_node_window.assert_not_called()

    def test_clears_restarting_set_on_completion(self, temp_db):
        """The node name is removed from _restarting_nodes after restart completes."""
        node_id = _create_test_node(temp_db, name="clear-set", pane_id="%34")
        node = temp_db.get_node(node_id)

        from armada_ai.infrastructure.db_stats import _restart_counts
        _restart_counts.pop("clear-set", None)

        fake_result = MagicMock()
        fake_result.pane_id = "%35"
        fake_result.session_id = "armada-test"
        _tmux.create_node_window.return_value = fake_result

        server_mod._auto_restart_node(node)

        assert "clear-set" not in server_mod._restarting_nodes

    def test_clears_restarting_set_on_failure(self, temp_db):
        """The node name is removed from _restarting_nodes even if restart fails."""
        node_id = _create_test_node(temp_db, name="fail-restart", pane_id="%36")
        node = temp_db.get_node(node_id)

        from armada_ai.infrastructure.db_stats import _restart_counts
        _restart_counts.pop("fail-restart", None)

        _tmux.create_node_window.side_effect = RuntimeError("tmux error")

        server_mod._auto_restart_node(node)

        assert "fail-restart" not in server_mod._restarting_nodes

        # Reset side_effect
        _tmux.create_node_window.side_effect = None


# --- _resurrect_dead_nodes ---


class TestResurrectDeadNodes:
    """Tests for _resurrect_dead_nodes."""

    def test_revives_dead_node_with_live_pane(self, temp_db):
        """A dead node whose tmux pane is still alive gets marked idle."""
        node_id = _create_test_node(temp_db, name="zombie", pane_id="%40")
        # Kill it first
        temp_db.kill_node(node_id)

        node = temp_db.get_node(node_id)
        assert node.status == "dead"

        _tmux.pane_alive.return_value = True

        server_mod._resurrect_dead_nodes()

        node = temp_db.get_node(node_id)
        assert node.status == "idle"

    def test_does_not_revive_dead_node_with_dead_pane(self, temp_db):
        """A dead node whose pane is also dead stays dead."""
        node_id = _create_test_node(temp_db, name="truly-dead", pane_id="%41")
        temp_db.kill_node(node_id)

        _tmux.pane_alive.return_value = False

        server_mod._resurrect_dead_nodes()

        node = temp_db.get_node(node_id)
        assert node.status == "dead"

    def test_does_not_revive_dead_node_without_pane_id(self, temp_db):
        """A dead node with no pane_id is not resurrected."""
        node_id = _create_test_node(temp_db, name="no-pane-dead", pane_id=None)
        temp_db.kill_node(node_id)

        _tmux.pane_alive.return_value = True

        server_mod._resurrect_dead_nodes()

        node = temp_db.get_node(node_id)
        assert node.status == "dead"
