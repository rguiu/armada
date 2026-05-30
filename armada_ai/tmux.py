import subprocess
import shutil
import os
import time
from pathlib import Path

HOOKS_DIR = os.path.expanduser("~/.armada/hooks")
ARMADA_SESSION = "armada"

SKILL_FILES = ["armada-node.md", "armada-worker.md", "armada-orchestrator.md"]
_SKILLS_SRC = Path(__file__).parent.parent / "skills"


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

    for fname in SKILL_FILES:
        src = _SKILLS_SRC / fname
        dst = skills_dir / fname
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)

    return str(skills_dir)


def install_user_skills() -> list[str]:
    """Install armada skills to user-level skill directories.
    Checks ~/.opencode/skills/ and ~/.claude/skills/.
    Returns list of paths where skills were installed."""
    installed = []
    home = Path.home()

    for agent_dir, skills_subdir in [
        (home / ".opencode", home / ".opencode" / "skills"),
        (home / ".claude", home / ".claude" / "skills"),
    ]:
        if agent_dir.exists():
            skills_subdir.mkdir(parents=True, exist_ok=True)
            for fname in SKILL_FILES:
                src = _SKILLS_SRC / fname
                dst = skills_subdir / fname
                if src.exists():
                    shutil.copy2(src, dst)
            installed.append(str(skills_subdir))

    return installed


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
                f"exec {os.environ.get('SHELL', '/bin/zsh')} -l"
            )
    else:
        # bash or auto: just a shell with the env var set
        shell_cmd = (
            f"cd '{safe_dir}' && "
            f"printf '\\033]2;{name}\\033\\\\' && "
            f"export ARMADA_NODE_NAME='{safe_name}' && "
            f"exec {os.environ.get('SHELL', '/bin/zsh')} -l"
        )

    result = _tmux(
        "new-window", "-t", ARMADA_SESSION, "-n", name,
        shutil.which("bash") or "/bin/bash", "-c", shell_cmd,
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


def attach_node(name: str) -> str | None:
    """Open a terminal attached to the named tmux window.
    Returns None on success, or an error message string."""
    if not _has_tmux():
        return "tmux is not installed"

    # Already inside tmux: switch client to the window
    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", f"{ARMADA_SESSION}:{name}"])
        return None

    # Try AppleScript to open iTerm (works regardless of TERM_PROGRAM on macOS)
    result = _try_iterm_attach(name)
    if result is None:
        return None

    # Try Terminal.app
    result2 = _try_terminal_attach(name)
    if result2 is None:
        return None

    # Nothing worked — return the first error message
    return result or "Cannot auto-open terminal. Run: tmux attach -t armada"


def _try_iterm_attach(name: str) -> str | None:
    """Try opening a new iTerm tab attached to the node."""
    try:
        applescript = (
            f'tell application "iTerm"\n'
            f'  activate\n'
            f'  try\n'
            f'    tell current window\n'
            f'      set newTab to (create tab with default profile)\n'
            f'      tell current session of newTab\n'
            f'        set name to "{name}"\n'
            f'        write text "tmux attach -t {ARMADA_SESSION}:{name}"\n'
            f'      end tell\n'
            f'    end tell\n'
            f'  on error\n'
            f'    set newWindow to (create window with default profile)\n'
            f'    tell current session of newWindow\n'
            f'      set name to "{name}"\n'
            f'      write text "tmux attach -t {ARMADA_SESSION}:{name}"\n'
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


def _try_terminal_attach(name: str) -> str | None:
    """Try opening a Terminal.app window attached to the node."""
    try:
        applescript = (
            f'tell application "Terminal"\n'
            f'  activate\n'
            f'  do script "tmux attach -t {ARMADA_SESSION}:{name}"\n'
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


    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", f"{ARMADA_SESSION}:{name}"])
        return True

    if has_attached_clients():
        subprocess.run(["tmux", "select-window", "-t", f"{ARMADA_SESSION}:{name}"])
        return True

    term = os.environ.get("TERM_PROGRAM", "")
    if "iTerm" in term:
        applescript = (
            f'tell application "iTerm"\n'
            f'  if (count of windows) > 0 then\n'
            f'    tell current window to create tab with default profile command "tmux attach -t {ARMADA_SESSION}:{name}"\n'
            f'  else\n'
            f'    create window with default profile command "tmux attach -t {ARMADA_SESSION}:{name}"\n'
            f'  end if\n'
            f'end tell'
        )
        subprocess.run(["osascript", "-e", applescript])
        return True

    return False


def running_window_names() -> set[str]:
    if not _has_tmux():
        return set()
    result = _tmux("list-windows", "-t", ARMADA_SESSION, "-F", "#{window_name}")
    if result.returncode != 0:
        return set()
    return set(result.stdout.strip().split("\n"))


def agent_hook_instructions(agent_name: str) -> str:
    return f"""You are node "{agent_name}". You are being monitored by Armada.

Use curl to report your status:
- At the start of each response: `curl -s -X POST http://127.0.0.1:9100/api/report -H "Content-Type: application/json" -d '{{"name":"{agent_name}","status":"active","message":"<5-word task>"}}'`
- At the end of each response: `curl -s -X POST http://127.0.0.1:9100/api/report -H "Content-Type: application/json" -d '{{"name":"{agent_name}","status":"idle","message":""}}'`

Keep messages under 5 words.
"""


def save_agent_hook(agent_name: str):
    os.makedirs(HOOKS_DIR, exist_ok=True)
    path = os.path.join(HOOKS_DIR, f"{agent_name}.md")
    with open(path, "w") as f:
        f.write(agent_hook_instructions(agent_name))
    return path
