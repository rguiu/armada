import subprocess
import shutil
import os
import json
import time
import tempfile
import threading
from pathlib import Path

HOOKS_DIR = os.path.expanduser("~/.armada/hooks")
ARMADA_SESSION = "armada"
_attach_counter = 0


def _next_attach_id():
    global _attach_counter
    _attach_counter += 1
    return _attach_counter

SKILL_DIRS = ["armada-node", "armada-worker", "armada-orchestrator"]
_SKILLS_SRC = Path(__file__).parent.parent / "skills"
_HOOKS_SRC = Path(__file__).parent / "hooks"


def _write_zsh_startup(zdotdir: str, tools_dir: str):
    """Write .zshenv and .zshrc to ZDOTDIR, chaining to user's global configs."""
    home_zshenv = os.path.expanduser("~/.zshenv")
    home_zshrc = os.path.expanduser("~/.zshrc")

    # .zshenv: environment — chain to global
    with open(os.path.join(zdotdir, ".zshenv"), "w") as f:
        if os.path.exists(home_zshenv):
            f.write(f'[[ -f "{home_zshenv}" ]] && source "{home_zshenv}"\n')

    # .zshrc: interactive — chain to global, then add tools (user's .zshrc clobbers PATH!)
    with open(os.path.join(zdotdir, ".zshrc"), "w") as f:
        if os.path.exists(home_zshrc):
            f.write(f'[[ -f "{home_zshrc}" ]] && source "{home_zshrc}"\n')
        f.write(f'export PATH="{tools_dir}:$PATH"\n')
        armada_bash = str(Path(__file__).parent / "armada-bash.sh")
        if os.path.exists(armada_bash):
            f.write(f'source "{armada_bash}"\n')


def _has_tmux() -> bool:
    return shutil.which("tmux") is not None


def _tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def ensure_armada_session():
    if not _has_tmux():
        raise RuntimeError("tmux is not installed. Install with: brew install tmux")
    result = _tmux("has-session", "-t", ARMADA_SESSION)
    if result.returncode != 0:
        _tmux("new-session", "-d", "-s", ARMADA_SESSION, "-n", "overview")
        _tmux("set-option", "-t", ARMADA_SESSION, "set-titles", "on")
        _tmux("set-option", "-t", ARMADA_SESSION, "set-titles-string", "#{window_name}")


def install_skills(project_dir: str):
    """Copy armada skill files into a project's skills directory."""
    cwd = os.path.abspath(project_dir)

    # Try opencode first, then claude
    skills_dir = None
    for d in [".opencode", ".claude"]:
        sd = Path(cwd) / d / "skills"
        if (Path(cwd) / d).exists():
            skills_dir = sd
            break

    if not skills_dir:
        skills_dir = Path(cwd) / ".opencode" / "skills"

    skills_dir.mkdir(parents=True, exist_ok=True)

    for dname in SKILL_DIRS:
        src = _SKILLS_SRC / dname / "SKILL.md"
        if src.exists():
            dst_dir = skills_dir / dname
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst_dir / "SKILL.md")

    # Also copy the armada-pending plugin to the project
    plugin_src = _SKILLS_SRC.parent / ".opencode" / "plugin" / "armada-pending.ts"
    if plugin_src.exists():
        plugin_dst = Path(cwd) / ".opencode" / "plugin" / "armada-pending.ts"
        plugin_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin_src, plugin_dst)

    return str(skills_dir)


def install_user_skills() -> list[str]:
    """Install armada skills and plugin to user-level directories.
    Returns list of paths where skills were installed."""
    installed = []
    home = Path.home()

    for agent_dir, skills_subdir in [
        (home / ".config" / "opencode", home / ".config" / "opencode" / "skills"),
        (home / ".claude", home / ".claude" / "skills"),
    ]:
        agent_dir.mkdir(parents=True, exist_ok=True)
        skills_subdir.mkdir(parents=True, exist_ok=True)
        for dname in SKILL_DIRS:
            src = _SKILLS_SRC / dname / "SKILL.md"
            if src.exists():
                dst_dir = skills_subdir / dname
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst_dir / "SKILL.md")
        installed.append(str(skills_subdir))

    # Also install the armada-pending plugin globally (OpenCode)
    plugin_src = _SKILLS_SRC.parent / ".opencode" / "plugin" / "armada-pending.ts"
    if plugin_src.exists():
        plugin_dst = home / ".config" / "opencode" / "plugin" / "armada-pending.ts"
        plugin_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin_src, plugin_dst)

    # Install Claude Code hooks globally
    claude_hooks_dst = home / ".claude" / "hooks"
    claude_hooks_dst.mkdir(parents=True, exist_ok=True)
    for hook_file in ("claude-pre-tool.sh", "claude-post-tool.sh", "claude-stop.sh", "claude-permission.sh"):
        src = _HOOKS_SRC / hook_file
        if src.exists():
            dst = claude_hooks_dst / hook_file
            shutil.copy2(src, dst)
            dst.chmod(0o755)
    installed.append(str(claude_hooks_dst))

    return installed


def _deploy_pending_plugin(cwd: str):
    """Copy armada-pending.js and ensure opencode loads it."""
    src = _SKILLS_SRC.parent / ".opencode" / "plugin" / "armada-pending.js"
    if not src.exists():
        return

    # Copy plugin file
    dst_dir = Path(cwd) / ".opencode" / "plugin"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / "armada-pending.js")

    # Merge plugin into opencode.json (create or update)
    config_path = Path(cwd) / "opencode.json"
    try:
        if config_path.exists():
            # Merge: add plugin if not already present
            cfg = json.loads(config_path.read_text())
            plugins = cfg.setdefault("plugin", [])
            plugin_ref = ".opencode/plugin/armada-pending.js"
            if plugin_ref not in plugins:
                plugins.append(plugin_ref)
        else:
            cfg = {"$schema": "https://opencode.ai/config.json", "plugin": [".opencode/plugin/armada-pending.js"]}
        config_path.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


def _deploy_claude_hooks(cwd: str):
    """Install Claude Code hooks for status reporting."""
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

    if settings_path.exists():
        try:
            cfg = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, IOError):
            cfg = {}
    else:
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
            "hooks": [{"type": "command", "command": command, "timeout": 5}]
        }
        if not any(
            h.get("hooks", [{}])[0].get("command") == command
            for h in event_hooks if isinstance(h, dict)
        ):
            event_hooks.append(entry)

    settings_path.write_text(json.dumps(cfg, indent=2))


def create_node_window(name: str, colour: str, working_dir: str,
                       agent_type: str = "auto") -> str | None:
    if not _has_tmux():
        return None

    ensure_armada_session()

    cwd = os.path.abspath(working_dir)
    safe_dir = cwd.replace("'", "'\\''")
    safe_name = name.replace("'", "'\\''")

    # Install armada skills into the project so the agent loads them
    try:
        install_skills(cwd)
    except Exception:
        pass

    # For opencode nodes, copy the pending plugin and register it
    if agent_type == "opencode":
        _deploy_pending_plugin(cwd)

    # For claude nodes, install hooks for pending status detection
    if agent_type == "claude":
        try:
            _deploy_claude_hooks(cwd)
        except Exception:
            pass

    # Determine what to run in the tmux window
    if agent_type in ("opencode", "claude"):
        agent_bin = shutil.which(agent_type)
        if agent_bin:
            shell_cmd = (
                f"cd '{safe_dir}' && "
                f"printf '\\033]2;{name}\\033\\\\' && "
                f"export ARMADA_NODE_NAME='{safe_name}' && "
                f"exec {agent_bin}"
            )
        else:
            shell_cmd = (
                f"cd '{safe_dir}' && "
                f"printf '\\033]2;{name}\\033\\\\' && "
                f"export ARMADA_NODE_NAME='{safe_name}' && "
                f"exec {os.environ.get('SHELL', '/bin/zsh')}"
            )
    else:
        # bash or auto: inject armada tools via ZDOTDIR (chains user configs)
        tools_dir = Path(__file__).parent / "bin"
        zdotdir = tempfile.mkdtemp(prefix="_armada_zsh_")
        _write_zsh_startup(zdotdir, tools_dir)
        shell_cmd = (
            f"cd '{safe_dir}' && "
            f"printf '\\033]2;{name}\\033\\\\' && "
            f"export ARMADA_NODE_NAME='{safe_name}' && "
            f"export ZDOTDIR='{zdotdir}' && "
            f"echo '[armada] {safe_name} - tools ready' && "
            f"exec zsh"
        )

    result = _tmux(
        "new-window", "-t", ARMADA_SESSION, "-n", name,
        shell_cmd,
    )

    if result.returncode != 0:
        return None

    time.sleep(0.3)
    pane_result = _tmux("display-message", "-p", "-t", f"{ARMADA_SESSION}:{name}", "#{pane_id}")
    pane_id = pane_result.stdout.strip() if pane_result.returncode == 0 else None

    if pane_id:
        _tmux("set-window-option", "-t", f"{ARMADA_SESSION}:{name}",
              "pane-active-border-style", f"fg={colour}")
        _tmux("set-window-option", "-t", f"{ARMADA_SESSION}:{name}",
              "pane-border-style", f"fg={colour}")
        _tmux("set-window-option", "-t", f"{ARMADA_SESSION}:{name}",
              "automatic-rename", "off")
        _tmux("set-window-option", "-t", f"{ARMADA_SESSION}:{name}",
              "allow-rename", "off")

    return pane_id


def kill_node_window(name: str):
    if not _has_tmux():
        return
    _tmux("kill-window", "-t", f"{ARMADA_SESSION}:{name}")


def window_exists(name: str) -> bool:
    if not _has_tmux():
        return False
    result = _tmux("list-windows", "-t", ARMADA_SESSION, "-F", "#{window_name}")
    if result.returncode != 0:
        return False
    return name in result.stdout.strip().split("\n")


def has_attached_clients() -> bool:
    result = _tmux("list-clients", "-t", ARMADA_SESSION)
    return result.returncode == 0 and bool(result.stdout.strip())


def attach_node(name: str, colour: str = "#8b949e") -> str | None:
    """Open a terminal attached to the named tmux window.
    Returns None on success, or an error message string."""
    if not _has_tmux():
        return "tmux is not installed"

    _tmux("set-option", "-t", ARMADA_SESSION, "set-titles", "on")
    _tmux("set-option", "-t", ARMADA_SESSION, "set-titles-string", "#{window_name}")

    # Already inside tmux: switch client to the window
    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", f"{ARMADA_SESSION}:{name}"])
        return None

    # Try AppleScript to open iTerm (works regardless of TERM_PROGRAM on macOS)
    result = _try_iterm_attach(name, colour)
    if result is None:
        return None

    # Try Terminal.app
    result2 = _try_terminal_attach(name)
    if result2 is None:
        return None

    return result or "Cannot auto-open terminal. Run: tmux attach -t armada"


def _try_iterm_attach(name: str, colour: str) -> str | None:
    """Try opening a new iTerm tab attached to the node, with tab colour."""
    # Write colour escape sequences to a temp file (avoids AppleScript escaping hell)
    r, g, b = _hex_to_rgb(colour)
    attach_file = f"/tmp/_armada_attach_{os.getpid()}.sh"
    with open(attach_file, "w") as f:
        f.write(f"printf '\\033]6;1;bg;red;brightness;{r}\\a'\n")
        f.write(f"printf '\\033]6;1;bg;green;brightness;{g}\\a'\n")
        f.write(f"printf '\\033]6;1;bg;blue;brightness;{b}\\a'\n")
        f.write(f"exec tmux new-session -t {ARMADA_SESSION} -s _view_{name}_{os.getpid()}_{_next_attach_id()} \\; select-window -t {name}\n")

    try:
        applescript = (
            f'tell application "iTerm"\n'
            f'  activate\n'
            f'  try\n'
            f'    tell current window\n'
            f'      set newTab to (create tab with default profile)\n'
            f'      tell current session of newTab\n'
            f'        set name to "{name}"\n'
            f'        write text "source {attach_file} && rm -f {attach_file}"\n'
            f'      end tell\n'
            f'    end tell\n'
            f'  on error\n'
            f'    set newWindow to (create window with default profile)\n'
            f'    tell current session of newWindow\n'
            f'      set name to "{name}"\n'
            f'      write text "source {attach_file} && rm -f {attach_file}"\n'
            f'    end tell\n'
            f'  end try\n'
            f'end tell'
        )
        result = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return None
        return f"iTerm: {result.stderr.strip()}"
    except FileNotFoundError:
        return "osascript not available"
    except Exception as e:
        return f"iTerm error: {e}"


def _hex_to_rgb(hex_colour: str) -> tuple[int, int, int]:
    """Convert '#EF4444' to (r, g, b) tuple with 0-255 range."""
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _try_terminal_attach(name: str) -> str | None:
    """Try opening a Terminal.app window attached to the node."""
    try:
        tmux_cmd = f"tmux new-session -t {ARMADA_SESSION} -s _view_{name}_{os.getpid()}_{_next_attach_id()} \\; select-window -t {name}"
        attach_file = f"/tmp/_armada_term_attach_{os.getpid()}.sh"
        with open(attach_file, "w") as f:
            f.write(f"exec {tmux_cmd}\n")
        applescript = (
            f'tell application "Terminal"\n'
            f'  activate\n'
            f'  do script "source {attach_file} && rm -f {attach_file}"\n'
            f'end tell'
        )
        result = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return None
        return f"Terminal: {result.stderr.strip()}"
    except FileNotFoundError:
        return None
    except Exception as e:
        return f"Terminal error: {e}"


def send_keys(name: str, command: str):
    """Send a command to a node's tmux window via send-keys."""
    if not _has_tmux():
        return False
    target = f"{ARMADA_SESSION}:{name}"
    # Use set-buffer + paste-buffer for reliable delivery to TUI apps
    _tmux("set-buffer", command)
    _tmux("paste-buffer", "-t", target)
    time.sleep(0.1)
    result = _tmux("send-keys", "-t", target, "Enter")
    return result.returncode == 0


def send_initial_prompt(name: str, prompt: str, delay: float = 3.0):
    """Send an initial prompt to a node once the agent is ready.
    Waits for the agent process to start, then for its input prompt."""

    def _send():
        # Wait for the agent process to actually be running in the pane
        target = f"{ARMADA_SESSION}:{name}"
        for _ in range(60):
            time.sleep(1)
            result = _tmux("display-message", "-t", target, "-p", "#{pane_current_command}")
            if result.returncode == 0:
                cmd = result.stdout.strip().lower()
                if cmd in ("node", "claude", "opencode", "deno"):
                    break
        else:
            # Timeout — agent never appeared, send anyway
            send_keys(name, prompt)
            return

        # Agent process is running — now wait for its REPL to be ready
        time.sleep(delay)
        for _ in range(30):
            result = _tmux("capture-pane", "-t", target, "-p")
            if result.returncode == 0:
                content = result.stdout
                if ">" in content or "❯" in content or "cost" in content.lower():
                    time.sleep(0.5)
                    send_keys(name, prompt)
                    return
            time.sleep(1)
        # Timeout — send anyway
        send_keys(name, prompt)

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def running_window_names() -> set[str]:
    if not _has_tmux():
        return set()
    result = _tmux("list-windows", "-t", ARMADA_SESSION, "-F", "#{window_name}")
    if result.returncode != 0:
        return set()
    return set(result.stdout.strip().split("\n"))


def agent_hook_instructions(agent_name: str) -> str:
    return f"""You are node "{agent_name}". You are being monitored by Armada.

REPORT YOUR STATUS BEFORE AND AFTER EVERY ACTION using curl:

- Before any work: `curl -s -X POST http://127.0.0.1:9100/api/report -H "Content-Type: application/json" -d '{{"name":"{agent_name}","status":"active","message":"<short description of what you are about to do>"}}'`
- After completing work: `curl -s -X POST http://127.0.0.1:9100/api/report -H "Content-Type: application/json" -d '{{"name":"{agent_name}","status":"idle","message":"<what you just did>"}}'`

Keep messages under 10 words. Be specific: "spawning 3 workers", "polling children", "reading results", "summing apples", not generic "working".

Your activity is visible at http://127.0.0.1:9100
"""



def save_agent_hook(agent_name: str):
    os.makedirs(HOOKS_DIR, exist_ok=True)
    path = os.path.join(HOOKS_DIR, f"{agent_name}.md")
    with open(path, "w") as f:
        f.write(agent_hook_instructions(agent_name))
    return path
