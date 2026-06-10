"""Tests for armada_ai.service."""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call
from armada_ai import service


class TestInstall:
    def test_armada_not_found(self, monkeypatch):
        monkeypatch.setattr(service.shutil, "which", lambda _: None)
        monkeypatch.setattr(sys, "stderr", MagicMock())
        result = service.install()
        assert result is False

    def test_unsupported_platform(self, monkeypatch):
        monkeypatch.setattr(service.shutil, "which", lambda _: "/usr/local/bin/armada")
        monkeypatch.setattr(service.platform, "system", lambda: "Windows")
        monkeypatch.setattr(sys, "stderr", MagicMock())
        result = service.install()
        assert result is False


class TestInstallLaunchd:
    def test_installs_launchd(self, monkeypatch, tmp_path):
        launchd_dir = tmp_path / "LaunchAgents"
        monkeypatch.setattr(service.shutil, "which", lambda _: "/usr/local/bin/armada")
        monkeypatch.setattr(service.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(service.os.path, "expanduser", lambda _: str(tmp_path))
        monkeypatch.setattr(service.os, "environ", {"PATH": "/usr/bin:/bin"})

        run_cmds = []
        monkeypatch.setattr(service, "_run_cmd", lambda cmd: run_cmds.append(cmd))

        result = service.install()

        assert result is True
        plist_path = tmp_path / "Library" / "LaunchAgents" / "com.armada.daemon.plist"
        assert plist_path.exists()
        content = plist_path.read_text()
        assert "/usr/local/bin/armada" in content
        assert str(tmp_path) in content
        assert "load" in run_cmds[-1]

    def test_installs_launchd_unload_existing(self, monkeypatch, tmp_path):
        launchd_dir = tmp_path / "Library" / "LaunchAgents"
        launchd_dir.mkdir(parents=True)
        plist_path = launchd_dir / "com.armada.daemon.plist"
        plist_path.write_text("old")

        monkeypatch.setattr(service.shutil, "which", lambda _: "/usr/local/bin/armada")
        monkeypatch.setattr(service.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(service.os.path, "expanduser", lambda _: str(tmp_path))
        monkeypatch.setattr(service.os, "environ", {"PATH": "/usr/bin:/bin"})

        run_cmds = []
        monkeypatch.setattr(service, "_run_cmd", lambda cmd: run_cmds.append(cmd))

        service.install()

        assert ["launchctl", "unload", str(plist_path)] in run_cmds
        assert ["launchctl", "load", str(plist_path)] in run_cmds


class TestInstallSystemd:
    def test_installs_systemd(self, monkeypatch, tmp_path):
        monkeypatch.setattr(service.shutil, "which", lambda _: "/usr/bin/armada")
        monkeypatch.setattr(service.platform, "system", lambda: "Linux")
        monkeypatch.setattr(service.os.path, "expanduser", lambda _: str(tmp_path))
        monkeypatch.setattr(service.os, "environ", {"PATH": "/usr/bin:/bin"})

        run_cmds = []
        monkeypatch.setattr(service, "_run_cmd", lambda cmd: run_cmds.append(cmd))

        result = service.install()

        assert result is True
        unit_path = tmp_path / ".config" / "systemd" / "user" / "armada.service"
        assert unit_path.exists()
        content = unit_path.read_text()
        assert "/usr/bin/armada" in content

        # Check expected systemd commands
        cmd_strings = [" ".join(c) for c in run_cmds]
        assert any("daemon-reload" in s for s in cmd_strings)
        assert any("enable" in s for s in cmd_strings)
        assert any("restart" in s for s in cmd_strings)

    def test_installs_systemd_stop_existing(self, monkeypatch, tmp_path):
        systemd_dir = tmp_path / ".config" / "systemd" / "user"
        systemd_dir.mkdir(parents=True)
        unit_path = systemd_dir / "armada.service"
        unit_path.write_text("old")

        monkeypatch.setattr(service.shutil, "which", lambda _: "/usr/bin/armada")
        monkeypatch.setattr(service.platform, "system", lambda: "Linux")
        monkeypatch.setattr(service.os.path, "expanduser", lambda _: str(tmp_path))
        monkeypatch.setattr(service.os, "environ", {"PATH": "/usr/bin:/bin"})

        run_cmds = []
        monkeypatch.setattr(service, "_run_cmd", lambda cmd: run_cmds.append(cmd))

        service.install()

        # First command should be stop
        cmd_strings = [" ".join(c) for c in run_cmds]
        assert any("stop" in s for s in cmd_strings)


class TestRunCmd:
    def test_runs_success(self, monkeypatch):
        import subprocess as sp
        mock_run = MagicMock()
        monkeypatch.setattr(sp, "run", mock_run)
        service._run_cmd(["echo", "hello"])
        mock_run.assert_called_once_with(["echo", "hello"], capture_output=True, timeout=10)

    def test_run_exception_is_silent(self, monkeypatch):
        import subprocess as sp
        mock_run = MagicMock(side_effect=Exception("boom"))
        monkeypatch.setattr(sp, "run", mock_run)
        service._run_cmd(["bad"])
