"""Skill, hook, and plugin deployment to projects and user profiles.

Extracted from tmux.py (install_skills, deploy_claude_hooks, etc.)
so tmux_session.py focuses purely on tmux operations.
"""
import json
import os
import shutil
from pathlib import Path

from . import tmux_session


SKILL_NAMES = ("armada-node", "armada-worker", "armada-orchestrator")
_SKILLS_SRC = Path(__file__).parent.parent.parent / "skills"
_HOOKS_SRC = Path(__file__).parent.parent / "hooks"
_PLUGIN_SRC_DIR = Path(__file__).parent.parent.parent / ".opencode" / "plugins"


def _resolve_agent_config_dir(cwd: str) -> tuple[Path | None, Path | None]:
    """Find .opencode or .claude config dir in the project."""
    project = Path(cwd)
    for d in (".opencode", ".claude"):
        agent_dir = project / d
        if agent_dir.exists():
            return agent_dir, agent_dir / "skills"
    return None, None


def install_skills_to_project(project_dir: str) -> str:
    """Copy armada skill files into a project's skills directory."""
    cwd = os.path.abspath(project_dir)
    _, skills_dir = _resolve_agent_config_dir(cwd)
    if skills_dir is None:
        skills_dir = Path(cwd) / ".opencode" / "skills"

    skills_dir.mkdir(parents=True, exist_ok=True)

    for dname in SKILL_NAMES:
        src = _SKILLS_SRC / dname / "SKILL.md"
        if src.exists():
            dst_dir = skills_dir / dname
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_dir / "SKILL.md")

    _deploy_pending_plugin(cwd)

    return str(skills_dir)


def install_skills_to_user() -> list[str]:
    """Install armada skills and plugins globally for the user."""
    installed = []
    home = Path.home()

    for agent_dir, skills_subdir in [
        (home / ".config" / "opencode", home / ".config" / "opencode" / "skills"),
        (home / ".claude", home / ".claude" / "skills"),
    ]:
        agent_dir.mkdir(parents=True, exist_ok=True)
        skills_subdir.mkdir(parents=True, exist_ok=True)
        for dname in SKILL_NAMES:
            src = _SKILLS_SRC / dname / "SKILL.md"
            if src.exists():
                dst_dir = skills_subdir / dname
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst_dir / "SKILL.md")
        installed.append(str(skills_subdir))

    _install_global_plugins(home)
    _install_global_claude_hooks(home)
    _install_global_mcp(home)
    return installed


def _deploy_pending_plugin(cwd: str):
    """Install armada-pending plugin files into a project."""
    project = Path(cwd)
    copies = []
    for dst_dir_name in ("plugins", "plugin"):
        dst_dir = project / ".opencode" / dst_dir_name
        dst_dir.mkdir(parents=True, exist_ok=True)
        for plugin_file in ("armada-pending.ts", "armada-pending.js"):
            src = _PLUGIN_SRC_DIR / plugin_file
            if src.exists():
                shutil.copy2(src, dst_dir / plugin_file)
                if plugin_file not in copies:
                    copies.append(plugin_file)

    if not copies:
        return

    config_path = project / "opencode.json"
    try:
        if config_path.exists():
            cfg = json.loads(config_path.read_text())
        else:
            cfg = {}
        cfg.setdefault("$schema", "https://opencode.ai/config.json")
        plugins = cfg.setdefault("plugin", [])
        for pf in copies:
            ref = f".opencode/plugins/{pf}"
            if ref not in plugins:
                plugins.append(ref)
        config_path.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


def _install_global_plugins(home: Path):
    for plugin_file in ("armada-pending.ts", "armada-pending.js"):
        src = _PLUGIN_SRC_DIR / plugin_file
        if src.exists():
            dst = home / ".config" / "opencode" / "plugins" / plugin_file
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _install_global_claude_hooks(home: Path):
    hooks_dst = home / ".claude" / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for hook_file in ("claude-pre-tool.sh", "claude-post-tool.sh",
                       "claude-stop.sh", "claude-permission.sh"):
        src = _HOOKS_SRC / hook_file
        if src.exists():
            dst = hooks_dst / hook_file
            shutil.copy2(src, dst)
            dst.chmod(0o755)


def _install_global_mcp(home: Path):
    mcp_entry = {"command": "armada", "args": ["mcp"]}

    oc_mcp = home / ".config" / "opencode" / "mcp.json"
    oc_mcp.parent.mkdir(parents=True, exist_ok=True)
    try:
        cfg = json.loads(oc_mcp.read_text()) if oc_mcp.exists() else {}
    except (json.JSONDecodeError, IOError):
        cfg = {}
    cfg.setdefault("mcpServers", {})["armada"] = mcp_entry
    oc_mcp.write_text(json.dumps(cfg, indent=2))

    cl_mcp = home / ".claude" / "mcp.json"
    cl_mcp.parent.mkdir(parents=True, exist_ok=True)
    try:
        cfg = json.loads(cl_mcp.read_text()) if cl_mcp.exists() else {}
    except (json.JSONDecodeError, IOError):
        cfg = {}
    cfg.setdefault("mcpServers", {})["armada"] = mcp_entry
    cl_mcp.write_text(json.dumps(cfg, indent=2))


def deploy_claude_hooks(cwd: str):
    """Install Claude Code hooks for status reporting into a project."""
    hooks_dst = Path(cwd) / ".claude" / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)

    hook_files = (
        "claude-pre-tool.sh", "claude-post-tool.sh",
        "claude-stop.sh", "claude-permission.sh",
    )
    for hook_file in hook_files:
        src = _HOOKS_SRC / hook_file
        if src.exists():
            dst = hooks_dst / hook_file
            shutil.copy2(src, dst)
            dst.chmod(0o755)

    settings_path = Path(cwd) / ".claude" / "settings.local.json"
    try:
        if settings_path.exists():
            cfg = json.loads(settings_path.read_text())
        else:
            cfg = {}
    except (json.JSONDecodeError, IOError):
        cfg = {}

    hooks = cfg.setdefault("hooks", {})
    hook_config = {
        "PreToolUse": ".claude/hooks/claude-pre-tool.sh",
        "PostToolUse": ".claude/hooks/claude-post-tool.sh",
        "Stop": ".claude/hooks/claude-stop.sh",
        "PermissionRequest": ".claude/hooks/claude-permission.sh",
    }
    for event, command in hook_config.items():
        event_hooks = hooks.setdefault(event, [])
        entry = {
            "matcher": "",
            "hooks": [{"type": "command", "command": command, "timeout": 5}],
        }
        if not any(
            h.get("hooks", [{}])[0].get("command") == command
            for h in event_hooks if isinstance(h, dict)
        ):
            event_hooks.append(entry)

    settings_path.write_text(json.dumps(cfg, indent=2))


def agent_hook_instructions(agent_name: str) -> str:
    workspace = tmux_session.agent_workspace(agent_name)
    return f"""You are node "{agent_name}". You are being monitored by Armada.

REPORT YOUR STATUS BEFORE AND AFTER EVERY ACTION using the `report_status` MCP tool:

- Before any work: `report_status(status="active", message="<short description>")`
- When waiting for user input: `report_status(status="pending", message="<what you need>")`
- After completing work: `report_status(status="idle", message="<what you did>")`

Use the Armada MCP tools for all node operations: `spawn_node`, `send_task`, `kill_node`, `get_tree`, `get_node`, `get_my_info`.

Keep messages under 10 words. Be specific: "spawning 3 workers", "polling children", "reading results", "summing apples", not generic "working".

PERSISTENT WORKSPACE: {workspace}
Save important output to your workspace — it survives node restarts.
export ARMADA_WORKSPACE="{workspace}"

Your activity is visible at http://127.0.0.1:9100
"""


def save_agent_hook(agent_name: str) -> str:
    from .. import constants
    os.makedirs(constants.HOOKS_DIR, exist_ok=True)
    path = os.path.join(constants.HOOKS_DIR, f"{agent_name}.md")
    with open(path, "w") as f:
        f.write(agent_hook_instructions(agent_name))
    return path


def _deploy_mcp_opencode(cwd: str):
    """Add Armada MCP server config to opencode.json."""
    config_path = Path(cwd) / "opencode.json"
    try:
        if config_path.exists():
            cfg = json.loads(config_path.read_text())
        else:
            cfg = {}
    except (json.JSONDecodeError, IOError):
        cfg = {}

    cfg.setdefault("$schema", "https://opencode.ai/config.json")
    mcp_servers = cfg.setdefault("mcpServers", {})
    mcp_servers["armada"] = {
        "command": "armada",
        "args": ["mcp"],
    }
    config_path.write_text(json.dumps(cfg, indent=2))


def _deploy_mcp_claude(cwd: str):
    """Add Armada MCP server config for Claude Code."""
    config_path = Path(cwd) / ".mcp.json"
    try:
        if config_path.exists():
            cfg = json.loads(config_path.read_text())
        else:
            cfg = {}
    except (json.JSONDecodeError, IOError):
        cfg = {}

    mcp_servers = cfg.setdefault("mcpServers", {})
    mcp_servers["armada"] = {
        "command": "armada",
        "args": ["mcp"],
    }
    config_path.write_text(json.dumps(cfg, indent=2))


def deploy_for_agent_type(agent_name: str, agent_type: str, cwd: str):
    """Install skills and agent-specific hooks/plugins for a new node."""
    from .. import logs
    try:
        install_skills_to_project(cwd)
    except Exception as e:
        logs.log_event("_server", "deploy_error",
                       {"step": "install_skills", "cwd": cwd, "error": str(e)})

    if agent_type == "opencode":
        try:
            _deploy_pending_plugin(cwd)
        except Exception as e:
            logs.log_event("_server", "deploy_error",
                           {"step": "pending_plugin", "cwd": cwd, "error": str(e)})
        try:
            _deploy_mcp_opencode(cwd)
        except Exception as e:
            logs.log_event("_server", "deploy_error",
                           {"step": "mcp_opencode", "cwd": cwd, "error": str(e)})

    if agent_type == "claude":
        try:
            deploy_claude_hooks(cwd)
        except Exception as e:
            logs.log_event("_server", "deploy_error",
                           {"step": "claude_hooks", "cwd": cwd, "error": str(e)})
        try:
            _deploy_mcp_claude(cwd)
        except Exception as e:
            logs.log_event("_server", "deploy_error",
                           {"step": "mcp_claude", "cwd": cwd, "error": str(e)})

    save_agent_hook(agent_name)
