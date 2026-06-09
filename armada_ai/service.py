import os
import sys
import platform
import shutil

LAUNCHD_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.armada.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>%%ARMADA_PATH%%</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>%%HOME%%/.armada/daemon.log</string>
    <key>StandardErrorPath</key>
    <string>%%HOME%%/.armada/daemon.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>%%PATH%%</string>
        <key>HOME</key>
        <string>%%HOME%%</string>
    </dict>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>"""

SYSTEMD_UNIT = """[Unit]
Description=Armada AI Agent Fleet
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%%ARMADA_PATH%% start
Restart=on-failure
RestartSec=10
Environment="PATH=%%PATH%%"
Environment="HOME=%%HOME%%"

[Install]
WantedBy=default.target
"""


def install():
    armada_path = shutil.which("armada")
    if not armada_path:
        print("armada not found in PATH. Install with: pip install armada-ai", file=sys.stderr)
        return False

    home = os.path.expanduser("~")
    path_env = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")

    system = platform.system()

    if system == "Darwin":
        return _install_launchd(armada_path, home, path_env)
    elif system == "Linux":
        return _install_systemd(armada_path, home, path_env)
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return False


def _install_launchd(armada_path: str, home: str, path_env: str) -> bool:
    launchd_dir = os.path.join(home, "Library", "LaunchAgents")
    plist_path = os.path.join(launchd_dir, "com.armada.daemon.plist")

    plist_content = LAUNCHD_PLIST.replace("%%ARMADA_PATH%%", armada_path)
    plist_content = plist_content.replace("%%HOME%%", home)
    plist_content = plist_content.replace("%%PATH%%", path_env)

    os.makedirs(launchd_dir, exist_ok=True)

    existing = None
    if os.path.exists(plist_path):
        existing = open(plist_path).read()
        _run_cmd(["launchctl", "unload", plist_path])

    with open(plist_path, "w") as f:
        f.write(plist_content)

    _run_cmd(["launchctl", "load", plist_path])
    print("Armada will start automatically on login.")
    print(f"To start now: launchctl start com.armada.daemon")
    print(f"To stop:       launchctl unload {plist_path}")
    return True


def _install_systemd(armada_path: str, home: str, path_env: str) -> bool:
    systemd_dir = os.path.join(home, ".config", "systemd", "user")
    unit_path = os.path.join(systemd_dir, "armada.service")

    unit_content = SYSTEMD_UNIT.replace("%%ARMADA_PATH%%", armada_path)
    unit_content = unit_content.replace("%%HOME%%", home)
    unit_content = unit_content.replace("%%PATH%%", path_env)

    os.makedirs(systemd_dir, exist_ok=True)

    existing = None
    if os.path.exists(unit_path):
        existing = open(unit_path).read()
        _run_cmd(["systemctl", "--user", "stop", "armada.service"])

    with open(unit_path, "w") as f:
        f.write(unit_content)

    _run_cmd(["systemctl", "--user", "daemon-reload"])
    _run_cmd(["systemctl", "--user", "enable", "armada.service"])
    _run_cmd(["systemctl", "--user", "restart", "armada.service"])
    print("Armada will start automatically on login.")
    print(f"To start now: systemctl --user start armada")
    print(f"To stop:      systemctl --user stop armada")
    print(f"Status:       systemctl --user status armada")
    return True


def _run_cmd(cmd: list[str]):
    import subprocess
    try:
        subprocess.run(cmd, capture_output=True, timeout=10)
    except Exception:
        pass
