"""Tests for API endpoints."""

import tempfile
import pytest
from unittest.mock import MagicMock


def _mkproj(temp_db, id="proj", name="Project"):
    """Helper: register a project label with a real temp directory."""
    path = tempfile.mkdtemp(prefix=f"armada_test_{id}_")
    temp_db.add_project_label(id, name, path)
    return path


class TestDashboard:
    def test_root_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "<html" in r.text.lower()


class TestTreeAndNodes:
    def test_tree_empty(self, temp_db, client):
        r = client.get("/api/tree")
        assert r.status_code == 200
        assert r.json() == []

    def test_tree_with_node(self, temp_db, client):
        _mkproj(temp_db, "proj", "Project")
        temp_db.create_node("aragorn", "#FF0000", project_label_id="proj")
        r = client.get("/api/tree")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "aragorn"

    def test_nodes_list(self, temp_db, client):
        temp_db.create_node("n1", "#111")
        temp_db.create_node("n2", "#222")
        r = client.get("/api/nodes")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_nodes_hide_dead(self, temp_db, client):
        _ = temp_db.create_node("living", "#111")
        temp_db.create_node("dying", "#222")
        temp_db.kill_node(temp_db.get_node_by_name("dying")["id"])
        r = client.get("/api/nodes?hide_dead=true")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "living"


class TestNodeCRUD:
    def test_create_node(self, temp_db, client):
        _mkproj(temp_db, "p", "P")
        r = client.post("/api/nodes", json={
            "name": "test-node",
            "project_label_id": "p",
            "agent_type": "bash",
        })
        assert r.status_code == 201
        assert r.json()["name"] == "test-node"
        assert r.json()["agent_type"] == "bash"

    def test_create_auto_name(self, temp_db, client):
        _mkproj(temp_db, "p", "P")
        r = client.post("/api/nodes", json={
            "project_label_id": "p",
            "agent_type": "bash",
        })
        assert r.status_code == 201
        assert r.json()["name"]

    def test_create_duplicate_name(self, temp_db, client):
        _mkproj(temp_db, "p", "P")
        client.post("/api/nodes", json={"name": "dup", "project_label_id": "p", "agent_type": "bash"})
        r = client.post("/api/nodes", json={"name": "dup", "project_label_id": "p", "agent_type": "bash"})
        assert r.status_code == 409

    def test_get_node_detail(self, temp_db, client):
        nid = temp_db.create_node("detail", "#333")
        temp_db.add_status_report(nid, "active", "working")
        r = client.get(f"/api/nodes/{nid}")
        assert r.status_code == 200
        data = r.json()
        assert data["node"]["name"] == "detail"
        assert len(data["reports"]) == 1

    def test_kill_node(self, temp_db, client):
        nid = temp_db.create_node("victim", "#444")
        r = client.delete(f"/api/nodes/{nid}")
        assert r.status_code == 200
        assert r.json()["killed"] == 1
        assert temp_db.get_node(nid)["status"] == "dead"

    def test_hide_node(self, temp_db, client):
        nid = temp_db.create_node("hidden", "#555")
        temp_db.kill_node(nid)  # must be dead first
        r = client.patch(f"/api/nodes/{nid}", json={"action": "hide"})
        assert r.status_code == 200
        assert r.json()["hidden"] == 1

    def test_get_node_404(self, client):
        r = client.get("/api/nodes/99999")
        assert r.status_code == 404

    def test_kill_404(self, client):
        r = client.delete("/api/nodes/99999")
        assert r.status_code == 404

    def test_create_node_nonexistent_project_path(self, temp_db, client):
        """Creating a node with a project label pointing to a nonexistent dir
        should return 400."""
        # Register a label with a fake path that doesn't exist on disk
        temp_db.add_project_label("ghost", "Ghost", "/nonexistent/path/12345")
        r = client.post("/api/nodes", json={
            "project_label_id": "ghost",
            "agent_type": "bash",
        })
        assert r.status_code == 400
        assert "does not exist" in r.json()["detail"]

    def test_create_node_project_label_not_found(self, temp_db, client):
        """Creating a node with an unknown project label should return 400."""
        r = client.post("/api/nodes", json={
            "project_label_id": "unknown-label",
            "agent_type": "bash",
        })
        assert r.status_code == 400
        assert "not found" in r.json()["detail"]

    def test_create_node_tmux_failure(self, temp_db, client):
        """When tmux create_node_window returns None, should return 500."""
        _mkproj(temp_db, "real", "Real Project")
        import armada_ai.tmux as tmux_mod
        orig = tmux_mod.create_node_window.return_value
        try:
            tmux_mod.create_node_window.return_value = None
            r = client.post("/api/nodes", json={
                "project_label_id": "real",
                "agent_type": "bash",
            })
            assert r.status_code == 500
            assert "tmux" in r.json()["detail"].lower()
        finally:
            tmux_mod.create_node_window.return_value = orig


class TestAgentReport:
    def test_report_active(self, temp_db, client):
        nid = temp_db.create_node("agent", "#666")
        r = client.post("/api/report", json={
            "name": "agent", "status": "active", "message": "working",
        })
        assert r.status_code == 200
        assert temp_db.get_node(nid)["status"] == "active"

    def test_report_pending(self, temp_db, client):
        nid = temp_db.create_node("waiter", "#777")
        r = client.post("/api/report", json={
            "name": "waiter", "status": "pending", "message": "need input",
        })
        assert r.status_code == 200
        assert temp_db.get_node(nid)["status"] == "pending"

    def test_report_unknown_node(self, client):
        r = client.post("/api/report", json={
            "name": "nobody", "status": "active", "message": "",
        })
        assert r.status_code == 404

    def test_report_invalid_status(self, temp_db, client):
        temp_db.create_node("agent2", "#888")
        r = client.post("/api/report", json={
            "name": "agent2", "status": "unknown", "message": "",
        })
        assert r.status_code == 400


class TestSendEndpoint:
    def test_send_to_bash_worker(self, temp_db, client):
        nid = temp_db.create_node("worker", "#999", agent_type="bash")
        r = client.post(f"/api/nodes/{nid}/send", json={
            "command": "echo test",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_send_missing_command(self, temp_db, client):
        nid = temp_db.create_node("w2", "#aaa")
        r = client.post(f"/api/nodes/{nid}/send", json={"command": ""})
        assert r.status_code == 400

    def test_send_to_dead_node(self, temp_db, client):
        nid = temp_db.create_node("deadw", "#bbb")
        temp_db.kill_node(nid)
        r = client.post(f"/api/nodes/{nid}/send", json={"command": "x"})
        assert r.status_code == 410


class TestProjectLabels:
    def test_list_empty(self, client):
        r = client.get("/api/project-labels")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_and_list(self, temp_db, client):
        proj_path = tempfile.mkdtemp(prefix="armada_test_myproj_")
        r = client.post("/api/project-labels", json={
            "id": "myproj", "name": "My Project", "path": proj_path,
        })
        assert r.status_code == 201
        labels = client.get("/api/project-labels").json()
        assert len(labels) == 1
        assert labels[0]["id"] == "myproj"

    def test_delete(self, temp_db, client):
        proj_path = tempfile.mkdtemp(prefix="armada_test_x_")
        client.post("/api/project-labels", json={"id": "x", "name": "X", "path": proj_path})
        r = client.delete("/api/project-labels/x")
        assert r.status_code == 200
        assert client.get("/api/project-labels").json() == []

    def test_create_missing_fields(self, client):
        """Missing id or name should return 400."""
        r = client.post("/api/project-labels", json={"id": "", "name": ""})
        assert r.status_code == 400


class TestRemainingEndpoints:
    def test_patch_unknown_action(self, temp_db, client):
        """PATCH with an unknown action should return 400."""
        nid = temp_db.create_node("patchable", "#aaa")
        r = client.patch(f"/api/nodes/{nid}", json={"action": "invalid_action"})
        assert r.status_code == 400

    def test_send_to_nonexistent_node(self, client):
        """Send to non-existent node should return 404."""
        r = client.post("/api/nodes/99999/send", json={"command": "echo hi"})
        assert r.status_code == 404

    def test_terminal_view(self, temp_db, client, monkeypatch):
        """GET /api/nodes/{id}/terminal returns pane content and dimensions."""
        import armada_ai.server as server_mod

        nid = temp_db.create_node("termtest", "#111")

        call_count = 0
        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if "display-message" in cmd:
                m.returncode = 0
                m.stdout = b"214 52"
            elif "capture-pane" in cmd:
                m.returncode = 0
                m.stdout = b"line1\nline2\n"
            else:
                m.returncode = 0
                m.stdout = b""
            return m

        monkeypatch.setattr(server_mod.subprocess, "run", fake_run)

        r = client.get(f"/api/nodes/{nid}/terminal")
        assert r.status_code == 200
        data = r.json()
        assert data["cols"] == 214
        assert data["rows"] == 52
        assert "line1" in data["text"]
        assert "line2" in data["text"]

    def test_terminal_view_node_not_found(self, client):
        """Terminal view for non-existent node returns 404."""
        r = client.get("/api/nodes/99999/terminal")
        assert r.status_code == 404

    def test_terminal_view_window_gone(self, temp_db, client, monkeypatch):
        """Terminal view when window doesn't exist returns 410."""
        import armada_ai.server as server_mod

        nid = temp_db.create_node("deadwin", "#222")
        monkeypatch.setattr(server_mod.tmux, "window_exists", lambda _: False)

        r = client.get(f"/api/nodes/{nid}/terminal")
        assert r.status_code == 410

    def test_terminal_view_capture_fails(self, temp_db, client, monkeypatch):
        """Terminal view when capture-pane fails returns 500."""
        import armada_ai.server as server_mod

        nid = temp_db.create_node("failwin", "#333")

        def fake_run(cmd, **kwargs):
            m = MagicMock()
            if "display-message" in cmd:
                m.returncode = 0
                m.stdout = b"80 24"
            else:
                m.returncode = 1
                m.stdout = b""
            return m

        monkeypatch.setattr(server_mod.subprocess, "run", fake_run)

        r = client.get(f"/api/nodes/{nid}/terminal")
        assert r.status_code == 500

    def test_terminal_view_default_dims(self, temp_db, client, monkeypatch):
        """Terminal view uses default 80x24 when display-message fails."""
        import armada_ai.server as server_mod

        nid = temp_db.create_node("defdims", "#444")

        def fake_run(cmd, **kwargs):
            m = MagicMock()
            if "display-message" in cmd:
                m.returncode = 1
                m.stdout = b""
            else:
                m.returncode = 0
                m.stdout = b"hello\n"
            return m

        monkeypatch.setattr(server_mod.subprocess, "run", fake_run)

        r = client.get(f"/api/nodes/{nid}/terminal")
        assert r.status_code == 200
        data = r.json()
        assert data["cols"] == 80
        assert data["rows"] == 24

    def test_terminal_view_carriage_return_stripped(self, temp_db, client, monkeypatch):
        """Carriage returns are stripped from captured text."""
        import armada_ai.server as server_mod

        nid = temp_db.create_node("crnode", "#555")

        def fake_run(cmd, **kwargs):
            m = MagicMock()
            if "display-message" in cmd:
                m.returncode = 0
                m.stdout = b"10 2"
            else:
                m.returncode = 0
                m.stdout = b"hello\r\nworld\r\n"
            return m

        monkeypatch.setattr(server_mod.subprocess, "run", fake_run)

        r = client.get(f"/api/nodes/{nid}/terminal")
        assert r.status_code == 200
        data = r.json()
        assert "\r" not in data["text"]
        assert "hello" in data["text"]
        assert "world" in data["text"]

    def test_terminal_view_ansi_stripped(self, temp_db, client, monkeypatch):
        """ANSI escape codes are stripped from captured text."""
        import armada_ai.server as server_mod

        nid = temp_db.create_node("ansinode", "#666")

        def fake_run(cmd, **kwargs):
            m = MagicMock()
            if "display-message" in cmd:
                m.returncode = 0
                m.stdout = b"5 1"
            else:
                m.returncode = 0
                m.stdout = b"\x1b[38;2;255;0;0mRED\x1b[0m text\n"
            return m

        monkeypatch.setattr(server_mod.subprocess, "run", fake_run)

        r = client.get(f"/api/nodes/{nid}/terminal")
        assert r.status_code == 200
        data = r.json()
        assert "\x1b" not in data["text"]
        assert "RED" in data["text"]
        assert "text" in data["text"]

    def test_terminal_view_lines_padded(self, temp_db, client, monkeypatch):
        """Lines are padded to match pane column width."""
        import armada_ai.server as server_mod

        nid = temp_db.create_node("padnode", "#777")

        def fake_run(cmd, **kwargs):
            m = MagicMock()
            if "display-message" in cmd:
                m.returncode = 0
                m.stdout = b"20 2"
            else:
                m.returncode = 0
                m.stdout = b"short\nvery long line here\n"
            return m

        monkeypatch.setattr(server_mod.subprocess, "run", fake_run)

        r = client.get(f"/api/nodes/{nid}/terminal")
        assert r.status_code == 200
        data = r.json()
        assert data["cols"] == 20
        assert data["rows"] == 2
        # Two lines, each padded to 20 chars → 40 chars total, no newlines
        assert len(data["text"]) == 40
        assert "\n" not in data["text"]

    def test_nodes_history(self, temp_db, client):
        """Killed nodes should appear in history."""
        nid = temp_db.create_node("historian", "#ccc")
        temp_db.kill_node(nid)
        r = client.get("/api/nodes/history")
        assert r.status_code == 200
        data = r.json()
        assert any(n["name"] == "historian" for n in data)

    def test_get_node_reports(self, temp_db, client):
        """GET /api/nodes/{id}/reports should return report list."""
        nid = temp_db.create_node("reporter", "#ddd")
        temp_db.add_status_report(nid, "active", "reporting")
        r = client.get(f"/api/nodes/{nid}/reports")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["status"] == "active"

    def test_attach_existing_node(self, temp_db, client):
        """Attach to an existing node should return 200."""
        _mkproj(temp_db, "attachproj", "Attach Project")
        # Need to create through API so tmux mock has create_node_window
        client.post("/api/nodes", json={
            "name": "attachable", "project_label_id": "attachproj",
            "agent_type": "bash",
        })
        nid = temp_db.get_node_by_name("attachable")["id"]
        r = client.post(f"/api/nodes/{nid}/attach")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_attach_nonexistent_node(self, client):
        """Attach to non-existent node should return 404."""
        r = client.post("/api/nodes/99999/attach")
        assert r.status_code == 404

    def test_refresh_hooks(self, temp_db, client):
        """Refresh hooks should return updated project list."""
        proj_path = tempfile.mkdtemp(prefix="armada_test_hooks_")
        client.post("/api/project-labels", json={
            "id": "hooksproj", "name": "Hooks Project", "path": proj_path,
        })
        r = client.post("/api/refresh-hooks")
        assert r.status_code == 200
        assert "updated" in r.json()

    def test_create_node_with_parent(self, temp_db, client):
        """Creating a node with a parent_id should work."""
        _mkproj(temp_db, "parentproj", "Parent Project")
        r1 = client.post("/api/nodes", json={
            "name": "parent_node", "project_label_id": "parentproj",
            "agent_type": "bash",
        })
        assert r1.status_code == 201
        parent_id = r1.json()["id"]

        r2 = client.post("/api/nodes", json={
            "name": "child_node", "project_label_id": "parentproj",
            "agent_type": "bash", "parent_id": parent_id,
        })
        assert r2.status_code == 201
        assert r2.json()["parent_id"] == parent_id

    def test_create_node_bad_parent(self, temp_db, client):
        """Creating a node with non-existent parent should return 400."""
        _mkproj(temp_db, "orphanproj", "Orphan Project")
        r = client.post("/api/nodes", json={
            "name": "orphan", "project_label_id": "orphanproj",
            "agent_type": "bash", "parent_id": 99999,
        })
        assert r.status_code == 400
        assert "Parent" in r.json()["detail"]

    def test_create_node_with_initial_prompt(self, temp_db, client):
        """Creating a node with initial_prompt should work."""
        _mkproj(temp_db, "promptproj", "Prompt Project")
        r = client.post("/api/nodes", json={
            "name": "prompted", "project_label_id": "promptproj",
            "agent_type": "bash", "initial_prompt": "echo hello",
        })
        assert r.status_code == 201
        assert r.json()["name"] == "prompted"

    def test_create_node_default_agent(self, temp_db, client):
        """Omitting agent_type should default to 'auto'."""
        _mkproj(temp_db, "autop", "Auto Project")
        r = client.post("/api/nodes", json={
            "name": "auto_agent", "project_label_id": "autop",
        })
        assert r.status_code == 201
        assert r.json()["agent_type"] == "auto"

    def test_patch_node_404(self, client):
        """PATCH on non-existent node should return 404."""
        r = client.patch("/api/nodes/99999", json={"action": "hide"})
        assert r.status_code == 404

    def test_create_project_label_empty_path(self, client):
        """Creating a project label with no path should use cwd."""
        r = client.post("/api/project-labels", json={
            "id": "cwdtag", "name": "CWD Tag",
        })
        assert r.status_code == 201


class TestAuth:
    def test_api_requires_token(self, temp_db, client, monkeypatch):
        """API calls without token return 401."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")

        r = client.get("/api/nodes")
        assert r.status_code == 401

    def test_api_with_query_token(self, temp_db, client, monkeypatch):
        """API calls with valid token in query param succeed."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")

        r = client.get("/api/nodes?token=secret123")
        assert r.status_code == 200

    def test_api_with_bearer_token(self, temp_db, client, monkeypatch):
        """API calls with valid token in Authorization header succeed."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")

        r = client.get("/api/nodes", headers={"Authorization": "Bearer secret123"})
        assert r.status_code == 200

    def test_api_wrong_token(self, temp_db, client, monkeypatch):
        """API calls with wrong token return 401."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")

        r = client.get("/api/nodes?token=wrong")
        assert r.status_code == 401

    def test_auth_status_valid(self, client, monkeypatch):
        """Auth status with valid token returns true."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")

        r = client.get("/api/auth/status?token=secret123")
        assert r.json()["valid"] is True

    def test_auth_status_invalid(self, client, monkeypatch):
        """Auth status with invalid token returns false."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")

        r = client.get("/api/auth/status?token=wrong")
        assert r.json()["valid"] is False

    def test_report_exempt_from_auth(self, temp_db, client, monkeypatch):
        """Agent report endpoint is exempt from token requirement."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")
        temp_db.create_node("reporter", "#888")

        r = client.post("/api/report", json={
            "name": "reporter", "status": "active", "message": "working",
        })
        assert r.status_code == 200

    def test_dashboard_no_token(self, client, monkeypatch):
        """Dashboard page loads without token."""
        import armada_ai.server as server_mod
        monkeypatch.setattr(server_mod, "TOKEN", "secret123")

        r = client.get("/")
        assert r.status_code == 200
        assert "<html" in r.text.lower()

    def test_ensure_token_creates(self, monkeypatch, tmp_path):
        """ensure_token creates a new token if none exists."""
        import armada_ai.server as server_mod

        token_file = tmp_path / "token"
        monkeypatch.setattr(server_mod, "TOKEN_FILE", str(token_file))
        monkeypatch.setattr(server_mod, "TOKEN", "")
        token = server_mod._ensure_token()
        assert len(token) == 32
        assert token_file.read_text().strip() == token

    def test_ensure_token_reuses(self, monkeypatch, tmp_path):
        """ensure_token reuses existing token file."""
        import armada_ai.server as server_mod

        token_file = tmp_path / "token"
        token_file.write_text("existing-token-1234567890ab")
        monkeypatch.setattr(server_mod, "TOKEN_FILE", str(token_file))
        monkeypatch.setattr(server_mod, "TOKEN", "")
        token = server_mod._ensure_token()
        assert token == "existing-token-1234567890ab"

    def test_lan_ip_returns_string(self):
        """_lan_ip returns a non-empty string."""
        import armada_ai.server as server_mod
        ip = server_mod._lan_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_check_token_valid(self, monkeypatch):
        """_check_token returns True for valid Authorization header."""
        import armada_ai.server as server_mod
        from fastapi import Request
        from unittest.mock import MagicMock

        monkeypatch.setattr(server_mod, "TOKEN", "abc123")
        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {}
        mock_request.headers = {"Authorization": "Bearer abc123"}
        assert server_mod._check_token(mock_request) is True

    def test_check_token_query_param(self, monkeypatch):
        """_check_token returns True for valid query param."""
        import armada_ai.server as server_mod
        from fastapi import Request
        from unittest.mock import MagicMock

        monkeypatch.setattr(server_mod, "TOKEN", "abc123")
        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {"token": "abc123"}
        mock_request.headers = {}
        assert server_mod._check_token(mock_request) is True

    def test_check_token_invalid(self, monkeypatch):
        """_check_token returns False for invalid token."""
        import armada_ai.server as server_mod
        from fastapi import Request
        from unittest.mock import MagicMock

        monkeypatch.setattr(server_mod, "TOKEN", "abc123")
        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {}
        mock_request.headers = {}
        assert server_mod._check_token(mock_request) is False


class TestDBRemaining:
    def test_get_root_nodes(self, temp_db):
        """get_root_nodes should return nodes with no parent."""
        temp_db.create_node("root1", "#111")
        temp_db.create_node("root2", "#222")
        pid = temp_db.create_node("parent_node", "#333")
        temp_db.create_node("child_node", "#444", parent_id=pid)

        roots = temp_db.get_root_nodes()
        root_names = {n["name"] for n in roots}
        assert "root1" in root_names
        assert "root2" in root_names
        assert "parent_node" in root_names
        assert "child_node" not in root_names


class TestCLI:
    def test_print_token_exists(self, tmp_path, monkeypatch):
        """_print_token prints the token from file."""
        import armada_ai.cli as cli_mod

        token_file = tmp_path / "token"
        token_file.write_text("my-token-123")
        monkeypatch.setattr(cli_mod.os.path, "expanduser", lambda p: str(token_file) if "token" in p else p)

        import io
        import sys
        captured = io.StringIO()
        monkeypatch.setattr(sys, "stdout", captured)
        cli_mod._print_token()
        assert captured.getvalue().strip() == "my-token-123"

    def test_print_token_missing(self, tmp_path, monkeypatch):
        """_print_token exits 1 when no token file exists."""
        import armada_ai.cli as cli_mod

        monkeypatch.setattr(cli_mod.os.path, "expanduser", lambda p: str(tmp_path / "nonexistent"))

        with pytest.raises(SystemExit) as exc:
            cli_mod._print_token()
        assert exc.value.code == 1
