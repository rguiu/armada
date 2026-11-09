"""Tests for armada_ai.infrastructure.deployment module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from armada_ai.infrastructure import deployment


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


class TestDeployMcpOpencode:
    """Tests for _deploy_mcp_opencode."""

    def test_creates_fresh_opencode_json(self):
        """Creates opencode.json with armada MCP config when none exists."""
        cwd = tempfile.mkdtemp()
        deployment._deploy_mcp_opencode(cwd)

        config_path = Path(cwd) / "opencode.json"
        assert config_path.exists()
        cfg = _read_json(config_path)

        assert cfg["$schema"] == "https://opencode.ai/config.json"
        armada = cfg["mcp"]["servers"]["armada"]
        assert armada["type"] == "local"
        assert armada["command"][1] == "mcp"
        assert armada["enabled"] is True

    def test_preserves_existing_mcp_servers(self):
        """Preserves non-armada entries already under mcp.servers."""
        cwd = tempfile.mkdtemp()
        config_path = Path(cwd) / "opencode.json"
        existing = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "servers": {
                    "other-server": {"type": "local", "command": ["other", "serve"]},
                },
            },
        }
        config_path.write_text(json.dumps(existing))

        deployment._deploy_mcp_opencode(cwd)

        cfg = _read_json(config_path)
        assert "other-server" in cfg["mcp"]["servers"]
        assert cfg["mcp"]["servers"]["other-server"]["command"] == ["other", "serve"]
        assert "armada" in cfg["mcp"]["servers"]

    def test_migrates_legacy_direct_mcp_entries(self):
        """Moves legacy mcp.<name> entries into mcp.servers."""
        cwd = tempfile.mkdtemp()
        config_path = Path(cwd) / "opencode.json"
        existing = {
            "mcp": {
                "other-server": {"type": "local", "command": ["other", "serve"]},
            },
        }
        config_path.write_text(json.dumps(existing))

        deployment._deploy_mcp_opencode(cwd)

        cfg = _read_json(config_path)
        assert "other-server" not in cfg["mcp"]
        assert cfg["mcp"]["servers"]["other-server"]["command"] == ["other", "serve"]
        assert "armada" in cfg["mcp"]["servers"]

    def test_migrates_legacy_mcpservers_to_mcp_servers(self):
        """Moves legacy mcpServers entries into mcp.servers and removes old key."""
        cwd = tempfile.mkdtemp()
        config_path = Path(cwd) / "opencode.json"
        existing = {
            "$schema": "https://opencode.ai/config.json",
            "mcpServers": {
                "legacy-server": {"command": "legacy", "args": ["--serve"]},
            },
        }
        config_path.write_text(json.dumps(existing))

        deployment._deploy_mcp_opencode(cwd)

        cfg = _read_json(config_path)
        assert "mcpServers" not in cfg
        assert cfg["mcp"]["servers"]["legacy-server"]["command"] == "legacy"
        assert "armada" in cfg["mcp"]["servers"]

    def test_migration_does_not_overwrite_existing_mcp_entries(self):
        """If both servers and mcpServers exist, mcp.servers takes precedence."""
        cwd = tempfile.mkdtemp()
        config_path = Path(cwd) / "opencode.json"
        existing = {
            "mcpServers": {
                "shared": {"command": "legacy-version"},
            },
            "mcp": {
                "servers": {
                    "shared": {"type": "local", "command": ["new-version"]},
                },
            },
        }
        config_path.write_text(json.dumps(existing))

        deployment._deploy_mcp_opencode(cwd)

        cfg = _read_json(config_path)
        assert cfg["mcp"]["servers"]["shared"]["command"] == ["new-version"]
        assert "mcpServers" not in cfg

    def test_direct_mcp_entry_takes_precedence_over_mcpservers(self):
        """A direct mcp.<name> entry wins over an older mcpServers entry."""
        cwd = tempfile.mkdtemp()
        config_path = Path(cwd) / "opencode.json"
        existing = {
            "mcpServers": {
                "shared": {"command": "legacy-version"},
            },
            "mcp": {
                "shared": {"type": "local", "command": ["new-version"]},
            },
        }
        config_path.write_text(json.dumps(existing))

        deployment._deploy_mcp_opencode(cwd)

        cfg = _read_json(config_path)
        assert cfg["mcp"]["servers"]["shared"]["command"] == ["new-version"]
        assert "mcpServers" not in cfg
        assert "shared" not in cfg["mcp"]


class TestDeployMcpClaude:
    """Tests for _deploy_mcp_claude."""

    def test_creates_fresh_mcp_json(self):
        """Creates .mcp.json with armada entry when none exists."""
        cwd = tempfile.mkdtemp()
        deployment._deploy_mcp_claude(cwd)

        config_path = Path(cwd) / ".mcp.json"
        assert config_path.exists()
        cfg = _read_json(config_path)

        assert "mcpServers" in cfg
        assert "armada" in cfg["mcpServers"]
        assert cfg["mcpServers"]["armada"]["args"] == ["mcp"]

    def test_preserves_existing_mcpservers_entries(self):
        """Preserves non-armada entries in mcpServers."""
        cwd = tempfile.mkdtemp()
        config_path = Path(cwd) / ".mcp.json"
        existing = {
            "mcpServers": {
                "other-tool": {"command": "other-tool", "args": ["serve"]},
            }
        }
        config_path.write_text(json.dumps(existing))

        deployment._deploy_mcp_claude(cwd)

        cfg = _read_json(config_path)
        assert "other-tool" in cfg["mcpServers"]
        assert cfg["mcpServers"]["other-tool"]["args"] == ["serve"]
        assert "armada" in cfg["mcpServers"]


class TestDeployPendingPlugin:
    """Tests for _deploy_pending_plugin (OpenCode V2)."""

    def test_copies_v2_plugin_and_removes_v1_artifacts(self):
        cwd = Path(tempfile.mkdtemp())
        plugins_dir = cwd / ".opencode" / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "armada-pending.js").write_text("old v1 plugin")

        legacy_dir = cwd / ".opencode" / "plugin"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "armada-pending.ts").write_text("old v1 plugin")
        (legacy_dir / "armada-pending.js").write_text("old v1 plugin")

        deployment._deploy_pending_plugin(str(cwd))

        assert (plugins_dir / "armada-pending.ts").exists()
        assert "Plugin.define" in (plugins_dir / "armada-pending.ts").read_text()
        assert not (plugins_dir / "armada-pending.js").exists()
        assert not legacy_dir.exists()

    def test_migrates_deprecated_opencode_keys(self):
        cwd = Path(tempfile.mkdtemp())
        config_path = cwd / "opencode.json"
        config_path.write_text(json.dumps({
            "plugin": [".opencode/plugins/armada-pending.ts"],
            "command": {"armada": {"template": "do the thing"}},
            "skills": {"paths": [".opencode/skills"]},
        }))

        deployment._deploy_pending_plugin(str(cwd))

        cfg = _read_json(config_path)
        assert "plugin" not in cfg
        assert cfg["commands"]["armada"]["template"] == "do the thing"
        assert cfg["skills"] == [".opencode/skills"]

    def test_does_not_create_config_when_missing(self):
        cwd = Path(tempfile.mkdtemp())

        deployment._deploy_pending_plugin(str(cwd))

        assert (cwd / ".opencode" / "plugins" / "armada-pending.ts").exists()
        assert not (cwd / "opencode.json").exists()

    def test_bundled_plugin_is_v2(self):
        plugin = deployment._PLUGIN_SRC_DIR / "armada-pending.ts"
        text = plugin.read_text()

        assert "@opencode/plugin" in text
        assert "Plugin.define" in text
        assert "export const ArmadaPending" not in text
        assert "/tmp/armada-events.log" not in text


class TestInstallGlobal:
    """Tests for global OpenCode installation."""

    def test_global_mcp_merges_into_opencode_json(self):
        home = Path(tempfile.mkdtemp())
        with patch("shutil.which", return_value=None):
            deployment._install_global_mcp(home)

        cfg = _read_json(home / ".config" / "opencode" / "opencode.json")
        assert cfg["mcp"]["servers"]["armada"]["command"] == ["armada", "mcp"]
        # Current OpenCode does not read the old standalone mcp.json file.
        assert not (home / ".config" / "opencode" / "mcp.json").exists()
        # Claude legacy path is still written for the follow-up PR.
        assert (home / ".claude" / "mcp.json").exists()

    def test_global_plugin_copies_v2_and_removes_v1(self):
        home = Path(tempfile.mkdtemp())
        plugins_dir = home / ".config" / "opencode" / "plugins"
        plugins_dir.mkdir(parents=True)
        (plugins_dir / "armada-pending.js").write_text("old v1 plugin")

        deployment._install_global_plugins(home)

        assert (plugins_dir / "armada-pending.ts").exists()
        assert not (plugins_dir / "armada-pending.js").exists()


class TestInstallSkillsToProject:
    """Tests for install_skills_to_project."""

    def test_copies_skill_files(self):
        """Copies SKILL.md files into .opencode/skills/ subdirectories."""
        cwd = tempfile.mkdtemp()
        result = deployment.install_skills_to_project(cwd)

        skills_dir = Path(result)
        assert skills_dir.exists()

        for skill_name in deployment.SKILL_NAMES:
            skill_file = skills_dir / skill_name / "SKILL.md"
            assert skill_file.exists(), f"Missing {skill_name}/SKILL.md"

    def test_uses_existing_opencode_skills_dir(self):
        """Uses existing .opencode/skills if .opencode dir exists."""
        cwd = tempfile.mkdtemp()
        opencode_dir = Path(cwd) / ".opencode"
        opencode_dir.mkdir()

        result = deployment.install_skills_to_project(cwd)
        assert ".opencode/skills" in result

    def test_uses_existing_claude_skills_dir(self):
        """Uses existing .claude/skills if .claude dir exists."""
        cwd = tempfile.mkdtemp()
        claude_dir = Path(cwd) / ".claude"
        claude_dir.mkdir()

        result = deployment.install_skills_to_project(cwd)
        assert ".claude/skills" in result


class TestDeployForAgentType:
    """Tests for deploy_for_agent_type."""

    @patch.object(deployment, "save_agent_hook", return_value="/tmp/hook.md")
    @patch.object(deployment, "install_skills_to_project")
    @patch.object(deployment, "_deploy_pending_plugin")
    def test_opencode_agent_deploys_plugin_not_mcp(
        self, mock_plugin, mock_skills, mock_hook
    ):
        """For opencode agent_type, deploys pending plugin but NOT per-project MCP."""
        cwd = tempfile.mkdtemp()
        deployment.deploy_for_agent_type("node-1", "opencode", cwd)

        mock_skills.assert_called_once_with(cwd)
        mock_plugin.assert_called_once_with(cwd)
        mock_hook.assert_called_once_with("node-1")

    @patch.object(deployment, "save_agent_hook", return_value="/tmp/hook.md")
    @patch.object(deployment, "deploy_claude_hooks")
    @patch.object(deployment, "install_skills_to_project")
    def test_claude_agent_deploys_hooks_not_mcp(
        self, mock_skills, mock_hooks, mock_save
    ):
        """For claude agent_type, deploys hooks but NOT per-project MCP."""
        cwd = tempfile.mkdtemp()
        deployment.deploy_for_agent_type("node-2", "claude", cwd)

        mock_skills.assert_called_once_with(cwd)
        mock_hooks.assert_called_once_with(cwd)
        mock_save.assert_called_once_with("node-2")

    @patch.object(deployment, "save_agent_hook", return_value="/tmp/hook.md")
    @patch.object(deployment, "install_skills_to_project")
    def test_unknown_agent_type_only_installs_skills(
        self, mock_skills, mock_save
    ):
        """For an unknown agent_type, only installs skills."""
        cwd = tempfile.mkdtemp()
        deployment.deploy_for_agent_type("node-3", "unknown", cwd)

        mock_skills.assert_called_once_with(cwd)
        mock_save.assert_called_once_with("node-3")
