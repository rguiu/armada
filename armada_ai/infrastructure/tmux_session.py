"""Pure tmux session and window management.

Extracted from tmux.py — contains only tmux subprocess operations.
Deployment (skills, hooks, plugins) moved to deployment.py.
Terminal attach logic moved to terminal_attach.py.
"""
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .. import constants
from .. import logs

ARMADA_SESSION = "armada"

_zdotdirs: dict[str, str] = {}
_SKILLS_SRC = Path(__file__).parent.parent.parent / "skills"


def agent_session(name: str) -> str:
    return f"armada-{name}"


def agent_target(name: str) -> str:
    return agent_session(name)


def agent_workspace(name: str) -> str:
    return os.path.join(constants.WORKSPACES_DIR, name)


def has_tmux() -> bool:
    return shutil.which("tmux") is not None


def tmux(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def ensure_armada_session():
    if not has_tmux():
        raise RuntimeError("tmux is not installed")
    result = tmux("has-session", "-t", ARMADA_SESSION)
    if result.returncode != 0:
        tmux("new-session", "-d", "-s", ARMADA_SESSION, "-n", "overview")
        tmux("set-option", "-t", ARMADA_SESSION, "set-titles", "on")
        tmux("set-option", "-t", ARMADA_SESSION, "set-titles-string", "#{window_name}")


def _build_shell_command(name: str, colour: str, working_dir: str,
                         agent_type: str) -> str | None:
    """Build the shell command string for a new node window. Returns None on failure."""
    cwd = os.path.abspath(working_dir)
    safe_dir = shlex.quote(cwd)
    safe_name = name.replace("'", "'\\''")
    sanitize_prefix = _sanitize_env_prefix()
    workspace = agent_workspace(name)
    os.makedirs(workspace, exist_ok=True)
    safe_workspace = workspace.replace("'", "'\\''")

    if agent_type in ("opencode", "claude"):
        agent_bin = shutil.which(agent_type)
        if agent_bin:
            return (
                f"{sanitize_prefix}"
                f"cd '{safe_dir}' && "
                f"printf '\\033]2;{name}\\033\\\\' && "
                f"export ARMADA_NODE_NAME='{safe_name}' && "
                f"export ARMADA_WORKSPACE='{safe_workspace}' && "
                f"exec {agent_bin}"
            )
        else:
            return (
                f"{sanitize_prefix}"
                f"cd '{safe_dir}' && "
                f"printf '\\033]2;{name}\\033\\\\' && "
                f"export ARMADA_NODE_NAME='{safe_name}' && "
                f"export ARMADA_WORKSPACE='{safe_workspace}' && "
                f"exec {os.environ.get('SHELL', '/bin/zsh')}"
            )
    else:
        tools_dir = Path(__file__).parent / "bin"
        zdotdir = tempfile.mkdtemp(prefix="_armada_zsh_")
        _zdotdirs[name] = zdotdir
        _write_zsh_startup(zdotdir, tools_dir)
        return (
            f"{sanitize_prefix}"
            f"cd '{safe_dir}' && "
            f"printf '\\033]2;{name}\\033\\\\' && "
            f"export ARMADA_NODE_NAME='{safe_name}' && "
            f"export ARMADA_WORKSPACE='{safe_workspace}' && "
            f"export ZDOTDIR='{zdotdir}' && "
            f"echo '[armada] {safe_name} - tools ready' && "
            f"exec zsh"
        )


def create_node_window(name: str, colour: str, working_dir: str,
                       agent_type: str = "auto") -> str | None:
    if not has_tmux():
        return None

    ensure_armada_session()

    session = agent_session(name)
    existing = tmux("has-session", "-t", session)
    if existing.returncode == 0:
        tmux("kill-session", "-t", session)

    shell_cmd = _build_shell_command(name, colour, working_dir, agent_type)

    result = tmux("new-session", "-d", "-s", session, shell_cmd)
    if result.returncode != 0:
        return None

    pane_id = None
    for _ in range(5):
        time.sleep(0.3)
        pane_result = tmux("display-message", "-p", "-t", session, "#{pane_id}")
        if pane_result.returncode == 0:
            pid = pane_result.stdout.strip()
            if pid:
                pane_id = pid
                break

    if pane_id:
        tmux("set-option", "-t", session, "pane-active-border-style", f"fg={colour}")
        tmux("set-option", "-t", session, "pane-border-style", f"fg={colour}")
        tmux("set-option", "-t", session, "automatic-rename", "off")
        tmux("set-option", "-t", session, "allow-rename", "off")
    else:
        tmux("kill-session", "-t", session)
        _zdotdirs.pop(name, None)

    return pane_id


def kill_node_window(name: str):
    if not has_tmux():
        return
    tmux("kill-session", "-t", agent_session(name))


def capture_pane_content(name: str, max_lines: int = 200) -> str:
    if not has_tmux():
        return ""
    target = agent_session(name)
    result = tmux("capture-pane", "-p", "-t", target, "-S", f"-{max_lines}")
    if result.returncode != 0:
        return ""
    return result.stdout


def window_exists(name: str) -> bool:
    if not has_tmux():
        return False
    result = tmux("has-session", "-t", agent_session(name))
    return result.returncode == 0


def pane_alive(pane_id: str) -> bool:
    if not has_tmux() or not pane_id:
        return False
    result = tmux("display-message", "-t", pane_id, "-p", "#{pane_id}")
    return result.returncode == 0 and result.stdout.strip() == pane_id


def running_window_names() -> set[str]:
    if not has_tmux():
        return set()
    result = tmux("list-sessions", "-F", "#{session_name}")
    if result.returncode != 0:
        return set()
    names = set()
    prefix = "armada-"
    for s in result.stdout.strip().split("\n"):
        if s.startswith(prefix):
            names.add(s[len(prefix):])
    return names


def send_keys(name: str, command: str) -> bool:
    if not has_tmux():
        return False
    target = agent_target(name)
    lines = command.split("\n")
    for i, line in enumerate(lines):
        if i > 0:
            tmux("send-keys", "-t", target, "Enter")
        if line:
            result = tmux("send-keys", "-l", "-t", target, line)
            if result.returncode != 0:
                return False
    result = tmux("send-keys", "-t", target, "Enter")
    return result.returncode == 0


def send_raw_keys(name: str, keys: str) -> bool:
    if not has_tmux():
        return False
    target = agent_target(name)
    parts = keys.replace('\r\n', '\n').replace('\r', '\n')
    buf = []
    for ch in parts:
        if ch == '\n':
            _flush_raw_buf(target, buf)
            tmux("send-keys", "-t", target, "Enter")
        elif ch == '\t':
            _flush_raw_buf(target, buf)
            tmux("send-keys", "-t", target, "Tab")
        else:
            buf.append(ch)
    _flush_raw_buf(target, buf)
    return True


_ANSI_TO_TMUX = {
    '\x1b[A': 'Up',
    '\x1b[B': 'Down',
    '\x1b[C': 'Right',
    '\x1b[D': 'Left',
}


def _flush_raw_buf(target, buf):
    if not buf:
        return
    s = ''.join(buf)
    buf.clear()
    while s:
        matched = False
        for ansi, tmux_key in _ANSI_TO_TMUX.items():
            if s.startswith(ansi):
                tmux("send-keys", "-t", target, tmux_key)
                s = s[len(ansi):]
                matched = True
                break
        if not matched:
            i = 0
            while i < len(s) and not any(s[i:].startswith(a) for a in _ANSI_TO_TMUX):
                i += 1
            if i > 0:
                tmux("send-keys", "-l", "-t", target, s[:i])
                s = s[i:]


def send_initial_prompt(name: str, prompt: str, delay: float = 3.0):
    sentinel = threading.Semaphore(3)

    def _send():
        if not sentinel.acquire(blocking=False):
            send_keys(name, prompt)
            return
        try:
            target = agent_target(name)
            for _ in range(60):
                time.sleep(1)
                result = tmux("display-message", "-t", target, "-p", "#{pane_current_command}")
                if result.returncode == 0:
                    cmd = result.stdout.strip().lower()
                    if cmd in ("node", "claude", "opencode", "deno"):
                        break
            else:
                send_keys(name, prompt)
                return

            time.sleep(delay)
            for _ in range(30):
                result = tmux("capture-pane", "-t", target, "-p")
                if result.returncode == 0:
                    content = result.stdout
                    if ">" in content or "❯" in content or "cost" in content.lower():
                        time.sleep(0.5)
                        send_keys(name, prompt)
                        return
                time.sleep(1)
            send_keys(name, prompt)
        except Exception as e:
            logs.log_event("_server", "prompt_error", {"node": name, "error": str(e)})
            try:
                send_keys(name, prompt)
            except Exception as e2:
                logs.log_event("_server", "prompt_fallback_error",
                               {"node": name, "error": str(e2)})
        finally:
            sentinel.release()

    threading.Thread(target=_send, daemon=True).start()


def cleanup_stale_sessions():
    """Kill orphaned _view_* tmux sessions and remove stale temp files."""
    result = tmux("list-sessions", "-F", "#{session_name}")
    if result.returncode != 0:
        return
    for session in result.stdout.strip().split("\n"):
        if not session.startswith("_view_"):
            continue
        clients = tmux("list-clients", "-t", session)
        if clients.returncode != 0 or not clients.stdout.strip():
            tmux("kill-session", "-t", session)

    if has_tmux():
        running = running_window_names()
        stale = [n for n in list(_zdotdirs) if n not in running]
        for name in stale:
            zdotdir = _zdotdirs.pop(name, None)
            if zdotdir:
                try:
                    shutil.rmtree(zdotdir, ignore_errors=True)
                except Exception:
                    pass

    tmp = tempfile.gettempdir()
    now = time.time()
    for pattern in ("_armada_attach_", "_armada_term_attach_", "_armada_zsh_"):
        for f in Path(tmp).glob(f"{pattern}*"):
            try:
                if now - f.stat().st_mtime > 60:
                    if f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
                    else:
                        f.unlink()
            except OSError:
                pass


# --- Internal helpers ---

SENSITIVE_ENV_VARS = [
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN", "AWS_DEFAULT_REGION", "AWS_REGION",
    "AWS_PROFILE", "AWS_SHARED_CREDENTIALS_FILE", "AWS_CONFIG_FILE",
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_ACCESS_TOKEN",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CO_API_KEY",
    "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "DOCKER_PASSWORD", "DOCKER_USERNAME",
    "NPM_TOKEN", "NPM_AUTH_TOKEN",
    "PYPI_TOKEN", "PYPI_PASSWORD",
    "SLACK_TOKEN", "DISCORD_TOKEN", "DISCORD_WEBHOOK",
    "TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN",
    "HOMEBREW_GITHUB_API_TOKEN",
    "GITLAB_TOKEN", "GITLAB_PRIVATE_TOKEN",
    "DIGITALOCEAN_ACCESS_TOKEN",
    "HEROKU_API_KEY",
    "NETLIFY_AUTH_TOKEN",
    "VERCEL_TOKEN",
    "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_KEY",
    "SENTRY_AUTH_TOKEN", "SENTRY_DSN",
    "STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
]


def _sanitize_env_prefix() -> str:
    vars_to_unset = [v for v in SENSITIVE_ENV_VARS if v in os.environ]
    if not vars_to_unset:
        return ""
    return "unset " + " ".join(vars_to_unset) + " 2>/dev/null; "


def _write_zsh_startup(zdotdir: str, tools_dir: Path):
    home_zshenv = os.path.expanduser("~/.zshenv")
    home_zshrc = os.path.expanduser("~/.zshrc")

    with open(os.path.join(zdotdir, ".zshenv"), "w") as f:
        if os.path.exists(home_zshenv):
            f.write(f'[[ -f "{home_zshenv}" ]] && source "{home_zshenv}"\n')

    with open(os.path.join(zdotdir, ".zshrc"), "w") as f:
        if os.path.exists(home_zshrc):
            f.write(f'[[ -f "{home_zshrc}" ]] && source "{home_zshrc}"\n')
        f.write(f'export PATH="{tools_dir}:$PATH"\n')
        armada_bash = str(Path(__file__).parent.parent / "armada-bash.sh")
        if os.path.exists(armada_bash):
            f.write(f'source "{armada_bash}"\n')
