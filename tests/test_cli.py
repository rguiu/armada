"""Tests for armada_ai/cli.py — CLI dispatch, doctor, status, and projects commands."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import armada_ai.constants as constants
from armada_ai import cli

# The tmux mock lives in sys.modules, injected by conftest
_tmux = sys.modules["armada_ai.tmux"]


@pytest.fixture(autouse=True)
def _reset_mocks():
    yield
    _tmux.running_window_names.return_value = []
    _tmux.running_window_names.side_effect = None


# --- main() dispatch ---


class TestMainDispatch:
    """Verify main() routes to the correct handler based on argv."""

    def test_version_prints_version(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "version"])
        cli.main()
        out = capsys.readouterr().out
        assert f"armada {constants.VERSION}" in out

    def test_unknown_command_prints_usage_and_exits(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "bogus-command"])
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_doctor_dispatches(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "doctor"])
        with patch.object(cli, "_doctor") as mock_doctor:
            cli.main()
            mock_doctor.assert_called_once_with(nuke=False)

    def test_doctor_nuke_dispatches(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "doctor", "--nuke"])
        with patch.object(cli, "_doctor") as mock_doctor:
            cli.main()
            mock_doctor.assert_called_once_with(nuke=True)

    def test_status_dispatches(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "status"])
        with patch.object(cli, "_status") as mock_status:
            cli.main()
            mock_status.assert_called_once()

    def test_projects_dispatches(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "projects", "list"])
        with patch.object(cli, "_projects_cmd") as mock_proj:
            cli.main()
            mock_proj.assert_called_once_with(["list"])

    def test_start_dispatches_to_server(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "start"])
        with patch("armada_ai.cli._print_startup_info"), \
             patch("armada_ai.server.start_server") as mock_start, \
             patch("armada_ai.server._ensure_token"):
            cli.main()
            mock_start.assert_called_once()


# --- _status() ---


class TestStatus:
    """Tests for the _status command that hits /health."""

    def test_status_running(self, capsys):
        health_data = json.dumps({
            "version": "0.2.0",
            "uptime": 123.4,
            "agents": 5,
            "active": 3,
            "pending": 1,
            "idle": 1,
        }).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = health_data

        with patch("urllib.request.urlopen", return_value=mock_resp):
            cli._status()

        out = capsys.readouterr().out
        assert "running" in out
        assert "v0.2.0" in out
        assert "123s" in out
        assert "Agents: 5" in out

    def test_status_connection_refused(self, capsys):
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("refused")):
            cli._status()

        out = capsys.readouterr().out
        assert "not reachable" in out


# --- _doctor() ---


class TestDoctor:
    """Tests for the _doctor health-check command."""

    def test_doctor_clean_state(self, capsys, temp_db, monkeypatch):
        """No issues on a clean state (no sessions, no DB nodes)."""
        _tmux.running_window_names.return_value = []

        monkeypatch.setattr(cli, "_get_pid_from_port", lambda port=9100: None)

        _real_exists = os.path.exists

        with patch("os.path.exists") as mock_exists, \
             patch("os.path.isdir") as mock_isdir, \
             patch("glob.glob", return_value=[]):
            mock_exists.side_effect = lambda p: (
                True if p == constants.DB_PATH else
                False
            )
            mock_isdir.return_value = False
            cli._doctor(nuke=False)

        out = capsys.readouterr().out
        assert "Armada Doctor" in out
        assert "No armada windows found" in out

    def test_doctor_shows_live_windows(self, capsys, temp_db, monkeypatch):
        """Doctor reports live tmux windows."""
        _tmux.running_window_names.return_value = ["alpha", "beta"]

        monkeypatch.setattr(cli, "_get_pid_from_port", lambda port=9100: None)

        with patch("os.path.exists") as mock_exists, \
             patch("os.path.isdir") as mock_isdir, \
             patch("glob.glob", return_value=[]):
            mock_exists.side_effect = lambda p: (
                True if p == constants.DB_PATH else
                False
            )
            mock_isdir.return_value = False
            cli._doctor(nuke=False)

        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out

    def test_doctor_nuke_exits(self, capsys, temp_db, monkeypatch):
        """Doctor with --nuke kills sessions and exits."""
        _tmux.running_window_names.return_value = []

        monkeypatch.setattr(cli, "_get_pid_from_port", lambda port=9100: None)

        with patch("subprocess.run"), \
             patch("os.path.exists", return_value=False), \
             patch("os.path.isdir", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cli._doctor(nuke=True)
            assert exc_info.value.code == 0

        out = capsys.readouterr().out
        assert "--nuke" in out
        assert "Start fresh" in out


# --- _projects_cmd() ---


class TestProjectsCmd:
    """Tests for the projects subcommand (list, add, rm)."""

    def test_list_empty(self, capsys):
        """List projects when none exist."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([]).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp), \
             patch.object(cli, "_read_token", return_value="test-token"):
            cli._projects_cmd([])

        out = capsys.readouterr().out
        assert "No projects" in out

    def test_list_shows_projects(self, capsys):
        """List projects when projects exist."""
        projects_data = [
            {"id": "proj-1", "name": "My Project", "path": "/tmp/proj1"},
            {"id": "proj-2", "name": "Other", "path": "/tmp/proj2"},
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(projects_data).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp), \
             patch.object(cli, "_read_token", return_value="test-token"):
            cli._projects_cmd([])

        out = capsys.readouterr().out
        assert "proj-1" in out
        assert "My Project" in out
        assert "/tmp/proj1" in out
        assert "proj-2" in out

    def test_add_project(self, capsys):
        """Add a project via CLI."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen, \
             patch.object(cli, "_read_token", return_value="test-token"):
            cli._projects_cmd(["add", "my-proj", "My Project", "/tmp/path"])

        out = capsys.readouterr().out
        assert "Added project my-proj" in out

        # Verify the request was made with correct data
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        assert body["id"] == "my-proj"
        assert body["name"] == "My Project"
        assert body["path"] == "/tmp/path"

    def test_add_project_missing_args(self, capsys):
        """Add with insufficient arguments prints usage and exits."""
        with pytest.raises(SystemExit) as exc_info:
            cli._projects_cmd(["add", "only-id"])
        assert exc_info.value.code == 1

        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_remove_project(self, capsys):
        """Remove a project via CLI."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen, \
             patch.object(cli, "_read_token", return_value="test-token"):
            cli._projects_cmd(["rm", "my-proj"])

        out = capsys.readouterr().out
        assert "Removed project my-proj" in out

        # Verify DELETE request
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.method == "DELETE"
        assert "my-proj" in req.full_url

    def test_remove_project_missing_id(self, capsys):
        """Remove with no ID prints usage and exits."""
        with pytest.raises(SystemExit) as exc_info:
            cli._projects_cmd(["rm"])
        assert exc_info.value.code == 1

        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_list_server_unreachable(self, capsys):
        """List projects when server is unreachable exits with error."""
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("refused")), \
             patch.object(cli, "_read_token", return_value="test-token"):
            with pytest.raises(SystemExit) as exc_info:
                cli._projects_cmd([])
            assert exc_info.value.code == 1

        err = capsys.readouterr().err
        assert "Failed" in err
