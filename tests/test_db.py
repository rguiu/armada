"""Tests for database operations."""

import pytest


class TestProjectLabels:
    def test_add_and_list(self, temp_db):
        temp_db.add_project_label("test", "Test Project", "/tmp/test")
        labels = temp_db.list_project_labels()
        assert len(labels) == 1
        assert labels[0]["id"] == "test"
        assert labels[0]["name"] == "Test Project"

    def test_delete(self, temp_db):
        temp_db.add_project_label("x", "X", "/tmp/x")
        temp_db.delete_project_label("x")
        assert len(temp_db.list_project_labels()) == 0

    def test_unique_path(self, temp_db):
        temp_db.add_project_label("a", "A", "/tmp/shared")
        with pytest.raises(ValueError):
            temp_db.add_project_label("b", "B", "/tmp/shared")


class TestNodes:
    def test_create_and_get(self, temp_db):
        nid = temp_db.create_node("aragorn", "#FF0000", agent_type="opencode")
        node = temp_db.get_node(nid)
        assert node["name"] == "aragorn"
        assert node["agent_type"] == "opencode"
        assert node["status"] == "idle"

    def test_create_with_parent(self, temp_db):
        pid = temp_db.create_node("parent", "#0000FF")
        _ = temp_db.create_node("child", "#00FF00", parent_id=pid)
        children = temp_db.get_node_children(pid)
        assert len(children) == 1
        assert children[0]["name"] == "child"

    def test_kill_cascade(self, temp_db):
        pid = temp_db.create_node("p", "#111")
        cid = temp_db.create_node("c", "#222", parent_id=pid)
        killed = temp_db.kill_node(pid)
        assert len(killed) == 2
        assert temp_db.get_node(pid)["status"] == "dead"
        assert temp_db.get_node(cid)["status"] == "dead"

    def test_hide_cascade(self, temp_db):
        pid = temp_db.create_node("p", "#111")
        cid = temp_db.create_node("c", "#222", parent_id=pid)
        hidden = temp_db.hide_node(pid)
        assert len(hidden) == 2
        # Hidden nodes filtered from queries
        nodes = temp_db.get_all_nodes()
        assert not any(n["id"] == pid for n in nodes)
        assert not any(n["id"] == cid for n in nodes)

    def test_killed_not_in_live_only(self, temp_db):
        nid = temp_db.create_node("live", "#000")
        temp_db.kill_node(nid)
        live = temp_db.get_all_nodes(include_dead=False)
        assert not any(n["id"] == nid for n in live)

    def test_killed_in_full_list(self, temp_db):
        nid = temp_db.create_node("diesoon", "#000")
        temp_db.kill_node(nid)
        all_nodes = temp_db.get_all_nodes(include_dead=True)
        assert any(n["id"] == nid for n in all_nodes)


class TestStatusReports:
    def test_add_and_retrieve(self, temp_db):
        nid = temp_db.create_node("reporter", "#333")
        temp_db.add_status_report(nid, "active", "working on it")
        temp_db.add_status_report(nid, "idle", "done")

        node = temp_db.get_node(nid)
        assert node["status"] == "idle"

        reports = temp_db.get_node_reports(nid)
        assert len(reports) == 2
        statuses = {r["status"] for r in reports}
        assert statuses == {"active", "idle"}

    def test_pending_status(self, temp_db):
        nid = temp_db.create_node("waiter", "#444")
        temp_db.add_status_report(nid, "pending", "waiting for input")
        assert temp_db.get_node(nid)["status"] == "pending"


class TestNodeOperations:
    def test_reparent_node(self, temp_db):
        pid = temp_db.create_node("parent", "#111")
        cid = temp_db.create_node("child", "#222")
        temp_db.reparent_node(cid, pid)
        node = temp_db.get_node(cid)
        assert node["parent_id"] == pid

    def test_reparent_to_root(self, temp_db):
        pid = temp_db.create_node("parent", "#111")
        cid = temp_db.create_node("child", "#222", parent_id=pid)
        temp_db.reparent_node(cid, None)
        node = temp_db.get_node(cid)
        assert node["parent_id"] is None

    def test_update_node_status(self, temp_db):
        nid = temp_db.create_node("status_test", "#333")
        temp_db.update_node_status(nid, "active", "%1")
        node = temp_db.get_node(nid)
        assert node["status"] == "active"
        assert node["tmux_pane_id"] == "%1"

    def test_accumulate_cost(self, temp_db):
        nid = temp_db.create_node("cost_test", "#444")
        temp_db.accumulate_cost(nid, tokens_in=100, tokens_out=50, cost=0.05)
        temp_db.accumulate_cost(nid, tokens_in=50, tokens_out=25, cost=0.03)
        node = temp_db.get_node(nid)
        assert node["total_tokens_in"] == 150
        assert node["total_tokens_out"] == 75
        assert node["total_cost"] == pytest.approx(0.08, abs=0.001)


class TestSyncProjects:
    def test_sync_projects_from_json(self, temp_db, monkeypatch, tmp_path):
        import json
        projects_file = tmp_path / "projects.json"
        projects_data = [{"id": "jsonproj", "name": "JSON Project", "path": str(tmp_path)}]
        projects_file.write_text(json.dumps(projects_data))
        monkeypatch.setattr(temp_db, "PROJECTS_FILE", str(projects_file))
        temp_db._sync_projects_from_json()
        labels = temp_db.list_project_labels()
        assert any(lb["id"] == "jsonproj" for lb in labels)

    def test_sync_projects_creates_file(self, temp_db, monkeypatch, tmp_path):
        projects_file = tmp_path / "nonexistent.json"
        monkeypatch.setattr(temp_db, "PROJECTS_FILE", str(projects_file))
        temp_db.add_project_label("dblabel", "DB Label", str(tmp_path))
        temp_db._sync_projects_from_json()
        import json
        data = json.loads(projects_file.read_text())
        assert any(p["id"] == "dblabel" for p in data)

    def test_sync_projects_json_corrupt(self, temp_db, monkeypatch, tmp_path):
        projects_file = tmp_path / "corrupt.json"
        projects_file.write_text("{invalid json")
        monkeypatch.setattr(temp_db, "PROJECTS_FILE", str(projects_file))
        temp_db.add_project_label("goodlabel", "Good", str(tmp_path))
        temp_db._sync_projects_from_json()
        labels = temp_db.list_project_labels()
        assert any(lb["id"] == "goodlabel" for lb in labels)


class TestNodeByName:
    def test_find(self, temp_db):
        temp_db.create_node("gandalf", "#FFF")
        node = temp_db.get_node_by_name("gandalf")
        assert node["name"] == "gandalf"

    def test_dead_not_found(self, temp_db):
        nid = temp_db.create_node("saruman", "#000")
        temp_db.kill_node(nid)
        assert temp_db.get_node_by_name("saruman") is None

    def test_hidden_not_found(self, temp_db):
        nid = temp_db.create_node("sauron", "#000")
        temp_db.hide_node(nid)
        assert temp_db.get_node_by_name("sauron") is None


class TestWriteLock:
    def test_concurrent_creates(self, temp_db):
        """Multiple rapid creates should not deadlock."""
        import threading
        errors = []

        def create():
            try:
                temp_db.create_node("t" + str(threading.get_ident()), "#000")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
