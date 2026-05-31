import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock tmux BEFORE any armada import
_mock_tmux = MagicMock()
_mock_tmux._has_tmux.return_value = True
_mock_tmux.window_exists.return_value = True
_mock_tmux.send_keys.return_value = True
_mock_tmux.create_node_window.return_value = "%0"
_mock_tmux.kill_node_window.return_value = None
_mock_tmux.ensure_armada_session.return_value = None
_mock_tmux.install_skills.return_value = "/tmp/skills"
_mock_tmux.save_agent_hook.return_value = "/tmp/hook.md"
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
    import armada_ai.db as db_mod

    db_path = os.path.join(_test_dir, "armada.db")
    projects_file = os.path.join(_test_dir, "projects.json")

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    monkeypatch.setattr(db_mod, "DB_DIR", _test_dir)
    monkeypatch.setattr(db_mod, "PROJECTS_FILE", projects_file)
    db_mod.init_db()
    yield db_mod
    # Clean up ALL data between tests
    conn = db_mod._connect()
    conn.execute("DELETE FROM status_reports")
    conn.execute("DELETE FROM nodes")
    conn.execute("DELETE FROM project_labels")
    conn.commit()
    conn.close()
    # Also wipe the JSON cache so init_db doesn't restore labels
    try:
        os.remove(os.path.join(_test_dir, "projects.json"))
    except OSError:
        pass


@pytest.fixture
def client():
    """FastAPI TestClient."""
    from armada_ai.server import app
    from fastapi.testclient import TestClient
    return TestClient(app)
