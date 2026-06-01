"""Tests for tmux module functions.

These tests un-mock the tmux module from conftest to test the real
implementation, then mock only the underlying _tmux / _has_tmux calls.
"""

import sys
import subprocess
from unittest.mock import patch, call


def _real_tmux_module():
    """Import the actual tmux module, bypassing the conftest mock.
    Only removes the tmux module from sys.modules; leaves other
    armada_ai modules (db, server, etc.) intact so fixtures work."""
    if "armada_ai.tmux" in sys.modules:
        del sys.modules["armada_ai.tmux"]
    import armada_ai.tmux
    return armada_ai.tmux


def _make_completed(returncode=0, stdout="", stderr=""):
    """Helper to create a subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["tmux"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestSendKeys:
    def test_send_keys_single_line(self):
        """send_keys should use literal mode (-l) for TUI compatibility."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=True), \
             patch.object(tmux, "_tmux") as mock_tmux:
            mock_tmux.return_value = _make_completed()

            target = f"{tmux.ARMADA_SESSION}:test_node"
            result = tmux.send_keys("test_node", "hello world")

            assert result is True
            mock_tmux.assert_any_call("send-keys", "-l", "-t", target, "hello world")
            mock_tmux.assert_any_call("send-keys", "-t", target, "Enter")

    def test_send_keys_multi_line(self):
        """Multi-line commands should split on newlines with Enter between."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=True), \
             patch.object(tmux, "_tmux") as mock_tmux:
            mock_tmux.return_value = _make_completed()

            target = f"{tmux.ARMADA_SESSION}:test_node"
            result = tmux.send_keys("test_node", "line1\nline2\nline3")

            assert result is True
            # Verify Enter calls happen between and after lines
            enter_calls = [
                c for c in mock_tmux.call_args_list
                if c == call("send-keys", "-t", target, "Enter")
            ]
            assert len(enter_calls) == 3

    def test_send_keys_empty_lines(self):
        """Empty lines should still send Enter but skip empty -l send."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=True), \
             patch.object(tmux, "_tmux") as mock_tmux:
            mock_tmux.return_value = _make_completed()

            target = f"{tmux.ARMADA_SESSION}:test_node"
            result = tmux.send_keys("test_node", "a\n\nb")

            assert result is True
            enter_calls = [
                c for c in mock_tmux.call_args_list
                if c == call("send-keys", "-t", target, "Enter")
            ]
            assert len(enter_calls) == 3

    def test_send_keys_no_tmux(self):
        """Should return False when tmux is not installed."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=False):
            assert tmux.send_keys("any", "hello") is False

    def test_send_keys_subprocess_failure(self):
        """Should return False if a send-keys call fails."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=True), \
             patch.object(tmux, "_tmux") as mock_tmux:
            mock_tmux.side_effect = [
                _make_completed(returncode=1),
            ]
            assert tmux.send_keys("test_node", "hello") is False


class TestSendInitialPrompt:
    def test_agent_process_found(self):
        """Should detect agent process and attempt to send prompt."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=True), \
             patch.object(tmux, "_tmux") as mock_tmux, \
             patch.object(tmux, "send_keys") as mock_send_keys, \
             patch.object(tmux.time, "sleep"):
            mock_send_keys.return_value = True
            mock_tmux.side_effect = [
                _make_completed(stdout="opencode\n"),
                _make_completed(stdout="> hello there\n"),
            ]

            tmux.send_initial_prompt("test_node", "do work", delay=0)
            import time
            time.sleep(0.2)

            assert mock_send_keys.called

    def test_agent_never_appears(self):
        """Should send prompt anyway after timeout (agent detection fails)."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=True), \
             patch.object(tmux, "_tmux") as mock_tmux, \
             patch.object(tmux, "send_keys") as mock_send_keys, \
             patch.object(tmux.time, "sleep"):
            mock_send_keys.return_value = True
            mock_tmux.return_value = _make_completed(returncode=1)

            tmux.send_initial_prompt("test_node", "do work", delay=0)
            import time
            time.sleep(0.2)

            assert mock_send_keys.called

    def test_exception_recovery(self):
        """Exception in _send should still attempt to send prompt."""
        tmux = _real_tmux_module()
        with patch.object(tmux, "_has_tmux", return_value=True), \
             patch.object(tmux, "_tmux") as mock_tmux, \
             patch.object(tmux, "send_keys") as mock_send_keys, \
             patch.object(tmux.time, "sleep"):
            mock_send_keys.return_value = True
            mock_tmux.side_effect = RuntimeError("broken")

            tmux.send_initial_prompt("test_node", "do work", delay=0)
            import time
            time.sleep(0.2)

            assert mock_send_keys.called
