"""Tests for armada_ai/cli.py — CLI dispatch, doctor, status, and projects commands."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from armada_ai import cli, constants

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
        err = capsys.readouterr().err
        assert "usage:" in err.lower()
        assert "invalid choice" in err.lower()

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
        with patch("shutil.which", return_value="/usr/bin/tmux"), \
             patch("armada_ai.cli._print_startup_info"), \
             patch("armada_ai.server.start_server") as mock_start, \
             patch("armada_ai.server._ensure_token"):
            cli.main()
            mock_start.assert_called_once_with(
                daemon=True, open_browser=True, lan=False, keep_token=False
            )

    def test_start_foreground(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "start", "--foreground"])
        with patch("shutil.which", return_value="/usr/bin/tmux"), \
             patch("armada_ai.cli._print_startup_info"), \
             patch("armada_ai.server.start_server") as mock_start, \
             patch("armada_ai.server._ensure_token"):
            cli.main()
            assert mock_start.call_args.kwargs["daemon"] is False

    def test_global_flags_can_appear_after_command(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "status", "--lan", "--no-browser"])
        with patch.object(cli, "_status") as mock_status:
            cli.main()
            mock_status.assert_called_once_with(json_output=False)

    def test_version_flag(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "--version"])
        cli.main()
        assert f"armada {constants.VERSION}" in capsys.readouterr().out

    def test_help_lists_commands(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "commands:" in out
        assert "nodes" in out
        assert "agents" in out

    def test_nodes_json_and_all(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "nodes", "--all", "--json"])
        with patch.object(cli, "_print_nodes") as mock_nodes:
            cli.main()
            mock_nodes.assert_called_once_with(include_dead=True, json_output=True)

    def test_nodes_watch(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "nodes", "--watch"])
        with patch.object(cli, "_watch_nodes") as mock_watch:
            cli.main()
            mock_watch.assert_called_once_with()

    def test_agents_json(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["armada", "agents", "--json"])
        with patch("shutil.which", return_value=None):
            cli.main()
        data = json.loads(capsys.readouterr().out)
        assert any(row["id"] == "claude" for row in data)
        assert all(row["available"] is False for row in data)


# --- _status() ---


class TestStatus:
    """Tests for the _status command."""

    @staticmethod
    def _fake_api(info, summary):
        def _api_get(path):
            return info if path == "/api/info" else summary
        return _api_get

    def test_status_running(self, capsys):
        info = {"version": "0.2.0", "uptime": 123.4}
        summary = {"total_agents": 5, "active": 3, "pending": 1, "idle": 1}

        with patch.object(cli, "_api_get", side_effect=self._fake_api(info, summary)):
            cli._status()

        out = capsys.readouterr().out
        assert "running" in out
        assert "v0.2.0" in out
        assert "123s" in out
        assert "Agents: 5" in out

    def test_status_connection_refused(self, capsys):
        with patch.object(cli, "_api_get", side_effect=ConnectionRefusedError("refused")):
            cli._status()

        err = capsys.readouterr().err
        assert "not reachable" in err

    def test_status_json(self, capsys):
        info = {"version": "0.4.0", "uptime": 12.0}
        summary = {"total_agents": 3, "active": 1, "pending": 1, "idle": 1}

        with patch.object(cli, "_api_get", side_effect=self._fake_api(info, summary)):
            cli._status(json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data["agents"] == 3
        assert data["version"] == "0.4.0"

    def test_status_json_down(self, capsys):
        with patch.object(cli, "_api_get", side_effect=ConnectionRefusedError("refused")):
            cli._status(json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data == {"status": "down"}


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
        """Add a project via CLI, with optional id/name overrides."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "my-proj"}).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen, \
             patch.object(cli, "_read_token", return_value="test-token"):
            cli._projects_cmd([
                "add", "/tmp/path", "--name", "My Project", "--id", "my-proj",
            ])

        out = capsys.readouterr().out
        assert "Added project my-proj" in out

        # Verify the request was made with correct data
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        assert body["id"] == "my-proj"
        assert body["name"] == "My Project"
        assert body["path"] == "/tmp/path"

    def test_add_project_by_path(self, capsys):
        """A bare path is enough; the server derives id and name."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"id": "my-project", "name": "my-project", "path": "/tmp/my-project"}
        ).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen, \
             patch.object(cli, "_read_token", return_value="test-token"):
            cli._projects_cmd(["add", "/tmp/my-project"])

        out = capsys.readouterr().out
        assert "Added project my-project" in out

        req = mock_urlopen.call_args[0][0]
        assert json.loads(req.data) == {"path": "/tmp/my-project"}

    def test_add_project_missing_args(self, capsys):
        """Add with no path prints usage and exits."""
        with pytest.raises(SystemExit):
            cli._projects_cmd(["add"])

    def test_scan_lists_unregistered(self, capsys):
        """Scan only shows discovered folders that are not registered yet."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "roots": ["/tmp"],
            "projects": [
                {"name": "new", "path": "/tmp/new", "id": None},
                {"name": "old", "path": "/tmp/old", "id": "old"},
            ],
        }).encode()

        with patch("urllib.request.urlopen", return_value=mock_resp), \
             patch.object(cli, "_read_token", return_value="test-token"):
            cli._projects_cmd(["scan"])

        out = capsys.readouterr().out
        assert "new" in out
        assert "old" not in out

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


class TestWatchAddProject:
    """Tests for the Projects tab's [n]ew-project form."""

    def test_path_only_posts_path(self):
        with patch.object(cli, "_watch_form", return_value={"Path": "/tmp/proj"}), \
             patch.object(cli, "_api_post") as mock_post:
            err = cli._watch_add_project(None, None)
        assert err is None
        mock_post.assert_called_once_with("/api/project-labels", {"path": "/tmp/proj"})

    def test_form_asks_only_for_path(self):
        with patch.object(cli, "_watch_form", return_value=None) as mock_form, \
             patch.object(cli, "_api_post"):
            cli._watch_add_project(None, None)
        fields = mock_form.call_args[0][3]
        assert [f["label"] for f in fields if f.get("type") != "button"] == ["Path"]

    def test_missing_path_does_nothing(self):
        with patch.object(cli, "_watch_form", return_value={"Path": ""}), \
             patch.object(cli, "_api_post") as mock_post:
            assert cli._watch_add_project(None, None) is None
        mock_post.assert_not_called()

    def test_api_error_is_reported(self):
        with patch.object(cli, "_watch_form", return_value={"Path": "/tmp/proj"}), \
             patch.object(cli, "_api_post", side_effect=OSError("boom")):
            err = cli._watch_add_project(None, None)
        assert err is not None and err.startswith("Failed")


class TestStyle:
    """Tests for the small output-styling helpers."""

    def test_style_respects_no_color(self, monkeypatch):
        monkeypatch.setattr(cli, "_COLOR_MODE", "auto")
        monkeypatch.setenv("NO_COLOR", "1")
        assert cli._style("hello", "red") == "hello"

    def test_style_forced_color(self, monkeypatch):
        monkeypatch.setattr(cli, "_COLOR_MODE", "always")
        assert cli._style("hello", "red") == "\033[31mhello\033[0m"

    def test_visible_len_ignores_ansi(self, monkeypatch):
        monkeypatch.setattr(cli, "_COLOR_MODE", "always")
        assert cli._visible_len(cli._style("abc", "red")) == 3

    def test_table_renders_columns(self, capsys, monkeypatch):
        monkeypatch.setattr(cli, "_COLOR_MODE", "always")
        cli._table(
            ["NAME", "STATUS"],
            [["short", cli._style("active", "green")],
             ["long-name", cli._style("idle", "dim")]],
        )
        out = capsys.readouterr().out
        assert "NAME" in out
        assert "long-name" in out
        assert "\033[32m" in out
