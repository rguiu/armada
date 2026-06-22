"""Terminal attach logic for opening tmux sessions in native terminals.

Extracted from tmux.py — contains iTerm, Terminal.app, and Linux terminal launchers.
"""
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time

from . import tmux_session


def _hex_to_rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _escape_applescript(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def attach_to_node(name: str, colour: str = "#8b949e",
                   session_id: str | None = None) -> str | None:
    """Open a terminal attached to the named tmux session.
    Returns None on success, or an error message string."""
    if not tmux_session.has_tmux():
        return "tmux is not installed"

    tmux_session.cleanup_stale_sessions()
    session = session_id or tmux_session.agent_session(name)

    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", session])
        return None

    system = platform.system()

    if system == "Darwin":
        has_iterm = os.path.exists("/Applications/iTerm.app") or os.path.exists(
            os.path.expanduser("~/Applications/iTerm.app"))
        if has_iterm:
            result = _try_iterm_attach(name, colour, session_id)
            if result is None:
                return None
        result = _try_terminal_attach(name, session_id)
        if result is None:
            return None
        return "Cannot auto-open terminal. Run: tmux attach -t armada"
    else:
        return _try_linux_attach(name, colour, session_id)


def _try_iterm_attach(name: str, colour: str, session_id: str | None = None) -> str | None:
    r, g, b = _hex_to_rgb(colour)
    session = session_id or tmux_session.agent_session(name)
    attach_file = os.path.join(tempfile.gettempdir(), f"_armada_attach_{os.getpid()}.sh")
    with open(attach_file, "w") as f:
        f.write(f"printf '\\033]6;1;bg;red;brightness;{r}\\a'\n")
        f.write(f"printf '\\033]6;1;bg;green;brightness;{g}\\a'\n")
        f.write(f"printf '\\033]6;1;bg;blue;brightness;{b}\\a'\n")
        f.write(f"tmux attach-session -t '{session}' || {{ echo 'Failed to attach to tmux session: {session}'; read -p \"Press Enter to close...\"; }}\n")

    try:
        safe_name = _escape_applescript(name)
        applescript = (
            f'tell application "iTerm"\n'
            f'  activate\n'
            f'  try\n'
            f'    tell current window\n'
            f'      set newTab to (create tab with default profile)\n'
            f'      tell current session of newTab\n'
            f'        set name to "{safe_name}"\n'
            f'        write text "source {attach_file} && rm -f {attach_file}"\n'
            f'      end tell\n'
            f'    end tell\n'
            f'  on error\n'
            f'    set newWindow to (create window with default profile)\n'
            f'    tell current session of newWindow\n'
            f'      set name to "{safe_name}"\n'
            f'      write text "source {attach_file} && rm -f {attach_file}"\n'
            f'    end tell\n'
            f'  end try\n'
            f'end tell'
        )
        result = subprocess.run(["osascript", "-e", applescript],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return None
        _remove(attach_file)
        return f"iTerm: {result.stderr.strip()}"
    except FileNotFoundError:
        _remove(attach_file)
        return "osascript not available"
    except Exception as e:
        _remove(attach_file)
        return f"iTerm error: {e}"


def _try_terminal_attach(name: str, session_id: str | None = None) -> str | None:
    try:
        session = session_id or tmux_session.agent_session(name)
        tmux_cmd = f"tmux attach-session -t '{session}'"
        attach_file = os.path.join(tempfile.gettempdir(),
                                   f"_armada_term_attach_{os.getpid()}.sh")
        with open(attach_file, "w") as f:
            f.write(f"{tmux_cmd} || {{ echo 'Failed to attach'; read; }}\n")
        applescript = (
            f'tell application "Terminal"\n'
            f'  activate\n'
            f'  do script "source {attach_file} && rm -f {attach_file}"\n'
            f'end tell'
        )
        result = subprocess.run(["osascript", "-e", applescript],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return None
        _remove(attach_file)
        return f"Terminal: {result.stderr.strip()}"
    except FileNotFoundError:
        _remove(attach_file)
        return "osascript not available"
    except Exception as e:
        _remove(attach_file)
        return f"Terminal error: {e}"


def _try_linux_attach(name: str, colour: str = "#8b949e",
                       session_id: str | None = None) -> str | None:
    session = session_id or tmux_session.agent_session(name)
    tmux_cmd = f"tmux attach-session -t '{session}'"
    tmpdir = tempfile.gettempdir()
    attach_file = os.path.join(tmpdir, f"_armada_attach_{os.getpid()}.sh")
    r, g, b = _hex_to_rgb(colour)
    with open(attach_file, "w") as f:
        f.write("#!/bin/bash\n")
        f.write(f"printf '\\033]6;1;bg;red;brightness;{r}\\a'\n")
        f.write(f"printf '\\033]6;1;bg;green;brightness;{g}\\a'\n")
        f.write(f"printf '\\033]6;1;bg;blue;brightness;{b}\\a'\n")
        f.write(f"{tmux_cmd} || {{ echo 'Failed to attach'; read; }}\n")
    os.chmod(attach_file, 0o700)

    def _cleanup():
        time.sleep(30)
        _remove(attach_file)
    threading.Thread(target=_cleanup, daemon=True).start()

    terminals = []
    for term_cmd in ["gnome-terminal", "konsole", "xfce4-terminal", "xterm",
                       "alacritty", "kitty", "terminator"]:
        if shutil.which(term_cmd):
            terminals.append(term_cmd)

    for term in terminals:
        try:
            if term == "gnome-terminal":
                subprocess.run(["gnome-terminal", "--", "bash", attach_file], timeout=3)
            elif term == "konsole":
                subprocess.run(["konsole", "-e", f"bash {attach_file}"], timeout=3)
            elif term == "xfce4-terminal":
                subprocess.run(["xfce4-terminal", "-e", f"bash {attach_file}"], timeout=3)
            elif term == "kitty":
                subprocess.run(["kitty", "bash", attach_file], timeout=3)
            elif term == "alacritty":
                subprocess.run(["alacritty", "-e", "bash", attach_file], timeout=3)
            elif term == "terminator":
                subprocess.run(["terminator", "-e", f"bash {attach_file}"], timeout=3)
            else:
                subprocess.run([term, "-e", f"bash {attach_file}"], timeout=3)
            return None
        except Exception:
            continue

    return "No terminal found. Install gnome-terminal, konsole, or xterm.\nRun: tmux attach -t armada"


def _remove(path: str):
    try:
        os.remove(path)
    except OSError:
        pass
