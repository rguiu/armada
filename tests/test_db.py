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
