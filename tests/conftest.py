import os
import sys
import atexit
import tempfile
import pytest
from unittest.mock import MagicMock

# Mock tmux BEFORE any armada import
_mock_tmux = MagicMock()
_mock_tmux._has_tmux.return_value = True
_mock_tmux.window_exists.return_value = True
_mock_tmux.send_keys.return_value = True
class _FakeNodeWindowResult:
    pane_id = "%0"
    session_id = "armada-test"
    error = None
    @property
    def ok(self):
        return True
_mock_tmux.create_node_window.return_value = _FakeNodeWindowResult()
_mock_tmux.kill_node_window.return_value = None
_mock_tmux.ensure_armada_session.return_value = None
_mock_tmux.install_skills.return_value = "/tmp/skills"
_mock_tmux.save_agent_hook.return_value = "/tmp/hook.md"
_mock_tmux.attach_node.return_value = None
_mock_tmux.send_initial_prompt.return_value = None
sys.modules["armada_ai.tmux"] = _mock_tmux

# Mock health to avoid background thread
_mock_health = MagicMock()
sys.modules["armada_ai.health"] = _mock_health

# Now safe to import
_test_dir = tempfile.mkdtemp(prefix="armada_test_")
os.environ["ARMADA_TEST_DIR"] = _test_dir


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Use a temporary SQLite database for every test."""
    import armada_ai.constants as const_mod
    import armada_ai.db as db_mod
    import armada_ai.server as server_mod

    db_path = os.path.join(_test_dir, "armada.db")
    projects_file = os.path.join(_test_dir, "projects.json")

    monkeypatch.setattr(const_mod, "DB_PATH", db_path)
    monkeypatch.setattr(const_mod, "DATA_DIR", _test_dir)
    monkeypatch.setattr(const_mod, "PROJECTS_FILE", projects_file)
    monkeypatch.setattr(server_mod, "TOKEN", "test-token")
    db_mod.init_db()
    yield db_mod
    db_mod.close_connection()
    # Clean up test files for next test
    try:
        db_file = os.path.join(_test_dir, "armada.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        for suffix in ("-wal", "-shm"):
            wf = db_file + suffix
            if os.path.exists(wf):
                os.remove(wf)
    except OSError:
        pass
    try:
        os.remove(os.path.join(_test_dir, "projects.json"))
    except OSError:
        pass


def _cleanup_db_connections():
    """Close any db connections from background threads (FastAPI/anyio)."""
    try:
        import armada_ai.db as db_mod
        db_mod.close_connection()
    except Exception:
        pass


atexit.register(_cleanup_db_connections)


@pytest.fixture
def client():
    """FastAPI TestClient with default auth token."""
    from armada_ai.server import app
    from fastapi.testclient import TestClient

    class AuthClient(TestClient):
        def request(self, method, url, **kwargs):
            headers = kwargs.get("headers") or {}
            headers.setdefault("Authorization", "Bearer test-token")
            kwargs["headers"] = headers
            return super().request(method, url, **kwargs)

    return AuthClient(app)
