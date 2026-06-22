"""Tests for armada_ai.infrastructure.deployment module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from armada_ai.infrastructure import deployment


class TestDeployMcpOpencode:
    """Tests for _deploy_mcp_opencode."""

    def test_creates_fresh_opencode_json(self):
        """Creates opencode.json with armada MCP config when none exists."""
        cwd = tempfile.mkdtemp()
        deployment._deploy_mcp_opencode(cwd)

        config_path = Path(cwd) / "opencode.json"
        assert config_path.exists()
        cfg = json.loads(config_path.read_text())

        assert cfg["$schema"] == "https://opencode.ai/config.json"
        assert "mcp" in cfg
        assert "armada" in cfg["mcp"]
        assert cfg["mcp"]["armada"]["type"] == "local"
        assert cfg["mcp"]["armada"]["command"][1] == "mcp"

    def test_preserves_existing_mcp_entries(self):
        """Preserves non-armada entries already under the 'mcp' key."""
        cwd = tempfile.mkdtemp()
        config_path = Path(cwd) / "opencode.json"
        existing = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "other-server": {"type": "local", "command": ["other", "serve"]},
            },
        }
        config_path.write_text(json.dumps(existing))

        deployment._deploy_mcp_opencode(cwd)

        cfg = json.loads(config_path.read_text())
        assert "other-server" in cfg["mcp"]
        assert cfg["mcp"]["other-server"]["command"] == ["other", "serve"]
        assert "armada" in cfg["mcp"]

    def test_migrates_legacy_mcpservers_to_mcp(self):
        """Moves legacy mcpServers entries into mcp and removes old key."""
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

        cfg = json.loads(config_path.read_text())
        # Legacy key should be removed
        assert "mcpServers" not in cfg
        # Legacy entries migrated into mcp
        assert "legacy-server" in cfg["mcp"]
        assert cfg["mcp"]["legacy-server"]["command"] == "legacy"
        # Armada entry also present
        assert "armada" in cfg["mcp"]

    def test_migration_does_not_overwrite_existing_mcp_entries(self):
        """If both mcp and mcpServers exist, mcp entries take precedence."""
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

        cfg = json.loads(config_path.read_text())
        # The mcp entry should not be overwritten by the legacy one
        assert cfg["mcp"]["shared"]["command"] == ["new-version"]
        assert "mcpServers" not in cfg


class TestDeployMcpClaude:
    """Tests for _deploy_mcp_claude."""

    def test_creates_fresh_mcp_json(self):
        """Creates .mcp.json with armada entry when none exists."""
        cwd = tempfile.mkdtemp()
        deployment._deploy_mcp_claude(cwd)

        config_path = Path(cwd) / ".mcp.json"
        assert config_path.exists()
        cfg = json.loads(config_path.read_text())

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

        cfg = json.loads(config_path.read_text())
        assert "other-tool" in cfg["mcpServers"]
        assert cfg["mcpServers"]["other-tool"]["args"] == ["serve"]
        assert "armada" in cfg["mcpServers"]


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
    @patch.object(deployment, "_deploy_mcp_opencode")
    @patch.object(deployment, "install_skills_to_project")
    @patch.object(deployment, "_deploy_pending_plugin")
    def test_opencode_agent_deploys_opencode_mcp(
        self, mock_plugin, mock_skills, mock_mcp_oc, mock_hook
    ):
        """For opencode agent_type, calls _deploy_mcp_opencode."""
        cwd = tempfile.mkdtemp()
        deployment.deploy_for_agent_type("node-1", "opencode", cwd)

        mock_skills.assert_called_once_with(cwd)
        mock_plugin.assert_called_once_with(cwd)
        mock_mcp_oc.assert_called_once_with(cwd)
        mock_hook.assert_called_once_with("node-1")

    @patch.object(deployment, "save_agent_hook", return_value="/tmp/hook.md")
    @patch.object(deployment, "_deploy_mcp_claude")
    @patch.object(deployment, "deploy_claude_hooks")
    @patch.object(deployment, "install_skills_to_project")
    def test_claude_agent_deploys_claude_mcp(
        self, mock_skills, mock_hooks, mock_mcp_cl, mock_save
    ):
        """For claude agent_type, calls _deploy_mcp_claude and deploy_claude_hooks."""
        cwd = tempfile.mkdtemp()
        deployment.deploy_for_agent_type("node-2", "claude", cwd)

        mock_skills.assert_called_once_with(cwd)
        mock_hooks.assert_called_once_with(cwd)
        mock_mcp_cl.assert_called_once_with(cwd)
        mock_save.assert_called_once_with("node-2")

    @patch.object(deployment, "save_agent_hook", return_value="/tmp/hook.md")
    @patch.object(deployment, "_deploy_mcp_opencode")
    @patch.object(deployment, "_deploy_mcp_claude")
    @patch.object(deployment, "install_skills_to_project")
    def test_unknown_agent_type_only_installs_skills(
        self, mock_skills, mock_mcp_cl, mock_mcp_oc, mock_save
    ):
        """For an unknown agent_type, only installs skills (no MCP deploy)."""
        cwd = tempfile.mkdtemp()
        deployment.deploy_for_agent_type("node-3", "unknown", cwd)

        mock_skills.assert_called_once_with(cwd)
        mock_mcp_oc.assert_not_called()
        mock_mcp_cl.assert_not_called()
        mock_save.assert_called_once_with("node-3")
