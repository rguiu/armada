"""Tests for API endpoints."""

import json


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
        temp_db.add_project_label("proj", "Project", "/tmp/proj")
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
        nid = temp_db.create_node("living", "#111")
        temp_db.create_node("dying", "#222")
        temp_db.kill_node(temp_db.get_node_by_name("dying")["id"])
        r = client.get("/api/nodes?hide_dead=true")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "living"


class TestNodeCRUD:
    def test_create_node(self, temp_db, client):
        temp_db.add_project_label("p", "P", "/tmp/p")
        r = client.post("/api/nodes", json={
            "name": "test-node",
            "project_label_id": "p",
            "agent_type": "bash",
        })
        assert r.status_code == 201
        assert r.json()["name"] == "test-node"
        assert r.json()["agent_type"] == "bash"

    def test_create_auto_name(self, temp_db, client):
        temp_db.add_project_label("p", "P", "/tmp/p")
        r = client.post("/api/nodes", json={
            "project_label_id": "p",
            "agent_type": "bash",
        })
        assert r.status_code == 201
        assert r.json()["name"]

    def test_create_duplicate_name(self, temp_db, client):
        temp_db.add_project_label("p", "P", "/tmp/p")
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
        r = client.post("/api/project-labels", json={
            "id": "myproj", "name": "My Project", "path": "/tmp/myproj",
        })
        assert r.status_code == 201
        labels = client.get("/api/project-labels").json()
        assert len(labels) == 1
        assert labels[0]["id"] == "myproj"

    def test_delete(self, temp_db, client):
        client.post("/api/project-labels", json={"id": "x", "name": "X", "path": "/tmp/x"})
        r = client.delete("/api/project-labels/x")
        assert r.status_code == 200
        assert client.get("/api/project-labels").json() == []
