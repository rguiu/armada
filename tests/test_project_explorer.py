"""Tests for project discovery."""
from armada_ai.project_explorer import discover_projects


def test_discover_finds_markers_and_skips_plain_folders(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    agent = tmp_path / "agent"
    (agent / ".opencode").mkdir(parents=True)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.json").write_text("{}")
    (tmp_path / "plain").mkdir()
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)

    found = {p["path"] for p in discover_projects([str(tmp_path)])}

    assert found == {str(repo), str(agent), str(pkg)}
