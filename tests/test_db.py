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


class TestRecover:
    def test_recover_nodes_marks_dead(self, temp_db):
        temp_db.create_node("alive1", "#111")
        temp_db.create_node("alive2", "#222")
        running = {"alive1"}
        temp_db.recover_nodes(running)
        assert temp_db.get_node_by_name("alive1") is not None
        assert temp_db.get_node_by_name("alive2") is None

    def test_recover_live_nodes_empty(self, temp_db):
        result = temp_db.recover_live_nodes(set())
        assert result == []

    def test_recover_live_nodes_finds_running(self, temp_db):
        nid = temp_db.create_node("runner", "#333")
        result = temp_db.recover_live_nodes({"runner"})
        assert len(result) == 1
        assert result[0]["name"] == "runner"

    def test_recover_live_nodes_skips_dead(self, temp_db):
        nid = temp_db.create_node("goner", "#444")
        temp_db.kill_node(nid)
        result = temp_db.recover_live_nodes({"goner"})
        assert result == []


class TestRenameNode:
    def test_rename(self, temp_db):
        nid = temp_db.create_node("oldname", "#555")
        temp_db.rename_node(nid, "newname")
        assert temp_db.get_node(nid)["name"] == "newname"


class TestKilledNodes:
    def test_get_killed_nodes(self, temp_db):
        nid = temp_db.create_node("goner2", "#666")
        temp_db.kill_node(nid)
        killed = temp_db.get_killed_nodes(limit=10)
        assert len(killed) >= 1
        assert any(k["name"] == "goner2" for k in killed)


class TestVacuumAndPrune:
    def test_vacuum_db(self, temp_db):
        temp_db.vacuum_db()

    def test_prune_all_old_reports(self, temp_db):
        nid = temp_db.create_node("pruner", "#777")
        for i in range(10):
            temp_db.add_status_report(nid, "active", f"msg {i}")
        temp_db.prune_all_old_reports(keep=5)
        reports = temp_db.get_node_reports(nid, limit=10)
        assert len(reports) <= 5


class TestLogCount:
    def test_increment_log_count(self, temp_db):
        nid = temp_db.create_node("logger", "#888")
        temp_db.increment_log_count(nid, 5)
        node = temp_db.get_node(nid)
        assert node["log_count"] == 5
        temp_db.increment_log_count(nid, 3)
        node = temp_db.get_node(nid)
        assert node["log_count"] == 8


class TestRestartCount:
    def test_restart_count_initial(self, temp_db):
        assert temp_db.get_restart_count_for_name("new-node") == 0

    def test_increment_restart_count(self, temp_db):
        temp_db.increment_restart_count("restarter")
        assert temp_db.get_restart_count_for_name("restarter") == 1
        temp_db.increment_restart_count("restarter")
        assert temp_db.get_restart_count_for_name("restarter") == 2


class TestQueries:
    def test_existing_names(self, temp_db):
        temp_db.create_node("n1", "#111")
        temp_db.create_node("n2", "#222")
        names = temp_db.existing_names()
        assert "n1" in names
        assert "n2" in names

    def test_existing_names_excludes_hidden(self, temp_db):
        nid = temp_db.create_node("visible", "#111")
        temp_db.create_node("hidden_one", "#222")
        nid_hidden = temp_db.get_node_by_name("hidden_one")["id"]
        temp_db.kill_node(nid_hidden)
        temp_db.hide_node(nid_hidden)
        names = temp_db.existing_names()
        assert "visible" in names
        assert "hidden_one" not in names

    def test_active_colours(self, temp_db):
        temp_db.create_node("c1", "#abc")
        temp_db.create_node("c2", "#def")
        colours = temp_db.active_colours()
        assert "#abc" in colours
        assert "#def" in colours


class TestGetNodesByProject:
    def test_get_nodes_by_project_label_id(self, temp_db):
        temp_db.add_project_label("p", "Project", "/tmp/p")
        temp_db.create_node("np1", "#111", project_label_id="p")
        temp_db.create_node("np2", "#222", project_label_id="p")
        nodes = temp_db.get_nodes_by_project_label_id("p")
        names = {n["name"] for n in nodes}
        assert "np1" in names
        assert "np2" in names


class TestBuildTree:
    def test_build_tree_flat(self, temp_db):
        temp_db.create_node("root1", "#111")
        temp_db.create_node("root2", "#222")
        tree = temp_db.build_tree(include_dead=True)
        assert len(tree) == 2

    def test_build_tree_nested(self, temp_db):
        pid = temp_db.create_node("parent", "#111")
        temp_db.create_node("child", "#222", parent_id=pid)
        tree = temp_db.build_tree(include_dead=True)
        assert len(tree) == 1
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["name"] == "child"

    def test_build_tree_excludes_dead(self, temp_db):
        nid = temp_db.create_node("live", "#111")
        nid2 = temp_db.create_node("dead", "#222")
        temp_db.kill_node(nid2)
        tree = temp_db.build_tree(include_dead=False)
        names = {n["name"] for n in tree}
        assert "live" in names
        assert "dead" not in names

    def test_build_tree_dead_node_with_parent(self, temp_db):
        pid = temp_db.create_node("p", "#aaa")
        cid = temp_db.create_node("c", "#bbb", parent_id=pid)
        temp_db.kill_node(pid)
        tree = temp_db.build_tree(include_dead=True)
        names = {n["name"] for n in tree}
        assert "p" in names or "c" in names


class TestCreateNodeReactivation:
    def test_create_reactivates_dead(self, temp_db):
        nid = temp_db.create_node("phoenix", "#111")
        temp_db.kill_node(nid)
        new_id = temp_db.create_node("phoenix", "#222")
        node = temp_db.get_node(new_id)
        assert node["status"] == "idle"
        assert node["colour"] == "#222"

    def test_create_reactivates_hidden(self, temp_db):
        nid = temp_db.create_node("returner", "#111")
        temp_db.kill_node(nid)
        temp_db.hide_node(nid)
        new_id = temp_db.create_node("returner", "#333")
        node = temp_db.get_node(new_id)
        assert node["status"] == "idle"
        assert node["colour"] == "#333"


class TestPruneReports:
    def test_prune_reports_threshold(self, temp_db):
        nid = temp_db.create_node("heavy", "#999")
        for i in range(55):
            temp_db.add_status_report(nid, "active", f"msg {i}")
        reports = temp_db.get_node_reports(nid, limit=300)
        assert len(reports) <= 200


class TestSyncProjectsEdgeCases:
    def test_sync_updates_existing(self, temp_db, monkeypatch, tmp_path):
        import json
        temp_db.add_project_label("up", "Old Name", str(tmp_path))

        projects_file = tmp_path / "projects.json"
        projects_data = [{"id": "up", "name": "New Name", "path": str(tmp_path)}]
        projects_file.write_text(json.dumps(projects_data))
        monkeypatch.setattr(temp_db, "PROJECTS_FILE", str(projects_file))

        temp_db._sync_projects_from_json()
        labels = temp_db.list_project_labels()
        label = next(lb for lb in labels if lb["id"] == "up")
        assert label["name"] == "New Name"

    def test_sync_json_has_extra_ids(self, temp_db, monkeypatch, tmp_path):
        import json
        db_path = tmp_path / "dbproj"
        db_path.mkdir()
        temp_db.add_project_label("indb", "In DB", str(db_path))

        json_path = tmp_path / "jsonproj"
        json_path.mkdir()
        projects_file = tmp_path / "projects.json"
        projects_data = [{"id": "injson", "name": "In JSON", "path": str(json_path)}]
        projects_file.write_text(json.dumps(projects_data))
        monkeypatch.setattr(temp_db, "PROJECTS_FILE", str(projects_file))

        temp_db._sync_projects_from_json()
        labels = temp_db.list_project_labels()
        ids = {lb["id"] for lb in labels}
        assert "indb" in ids
        assert "injson" in ids

    def test_sync_json_missing_file(self, temp_db, monkeypatch, tmp_path):
        temp_db.add_project_label("persist", "X", str(tmp_path))
        nonexistent = tmp_path / "does_not_exist.json"
        monkeypatch.setattr(temp_db, "PROJECTS_FILE", str(nonexistent))
        temp_db._sync_projects_from_json()
        labels = temp_db.list_project_labels()
        assert any(lb["id"] == "persist" for lb in labels)
