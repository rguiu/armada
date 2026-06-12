"""Tests for tmux module functions.

These tests un-mock the tmux module from conftest to test the real
implementation, then mock only the underlying tmux calls.
"""
import sys
import subprocess
from unittest.mock import patch, MagicMock, call


def _real_tmux_module():
    """Import the actual tmux module, bypassing the conftest mock."""
    for key in list(sys.modules):
        if key.startswith("armada_ai.tmux") or key.startswith("armada_ai.infrastructure.tmux"):
            del sys.modules[key]
    import armada_ai.tmux
    return armada_ai.tmux


def _make_completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["tmux"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _run_send_sync(tmux, name, prompt, delay=0):
    """Call send_initial_prompt but force the internal thread to run synchronously."""
    def run_sync(**kwargs):
        target = kwargs.get("target")
        if target:
            target()
        return MagicMock()

    with patch.object(tmux.threading, "Thread", side_effect=run_sync):
        tmux.send_initial_prompt(name, prompt, delay=delay)


class TestSendKeys:
    def test_send_keys_single_line(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        # Patch the implementation module directly
        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            result = tmux.send_keys("test_node", "hello world")

            assert result is True
            target = impl.agent_target("test_node")
            mock_run.assert_any_call("send-keys", "-l", "-t", target, "hello world")
            mock_run.assert_any_call("send-keys", "-t", target, "Enter")

    def test_send_keys_multi_line(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            target = impl.agent_target("test_node")
            result = tmux.send_keys("test_node", "line1\nline2\nline3")

            assert result is True
            enter_calls = [
                c for c in mock_run.call_args_list
                if c == call("send-keys", "-t", target, "Enter")
            ]
            assert len(enter_calls) == 3

    def test_send_keys_empty_lines(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            target = impl.agent_target("test_node")
            result = tmux.send_keys("test_node", "a\n\nb")

            assert result is True
            enter_calls = [
                c for c in mock_run.call_args_list
                if c == call("send-keys", "-t", target, "Enter")
            ]
            assert len(enter_calls) == 3

    def test_send_keys_no_tmux(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        with patch.object(impl, "has_tmux", return_value=False):
            assert tmux.send_keys("any", "hello") is False

    def test_send_keys_subprocess_failure(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed(returncode=1))
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            assert tmux.send_keys("test_node", "hello") is False


class TestSendRawKeys:
    def test_send_raw_keys_plain_text(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            result = tmux.send_raw_keys("test_node", "hello")
            assert result is True
            target = impl.agent_target("test_node")
            mock_run.assert_any_call("send-keys", "-l", "-t", target, "hello")

    def test_send_raw_keys_with_enter(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            result = tmux.send_raw_keys("test_node", "hi\n")
            assert result is True
            target = impl.agent_target("test_node")
            mock_run.assert_any_call("send-keys", "-l", "-t", target, "hi")
            mock_run.assert_any_call("send-keys", "-t", target, "Enter")

    def test_send_raw_keys_with_tab(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            result = tmux.send_raw_keys("test_node", "a\tb")
            assert result is True
            target = impl.agent_target("test_node")
            mock_run.assert_any_call("send-keys", "-l", "-t", target, "a")
            mock_run.assert_any_call("send-keys", "-t", target, "Tab")
            mock_run.assert_any_call("send-keys", "-l", "-t", target, "b")

    def test_send_raw_keys_ansi_down_arrow(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            result = tmux.send_raw_keys("test_node", "\x1b[B\n")
            assert result is True
            target = impl.agent_target("test_node")
            mock_run.assert_any_call("send-keys", "-t", target, "Down")
            mock_run.assert_any_call("send-keys", "-t", target, "Enter")

    def test_send_raw_keys_ansi_right_right_enter(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            result = tmux.send_raw_keys("test_node", "\x1b[C\x1b[C\n")
            assert result is True
            target = impl.agent_target("test_node")
            right_calls = [c for c in mock_run.call_args_list
                           if c == call("send-keys", "-t", target, "Right")]
            assert len(right_calls) == 2
            mock_run.assert_any_call("send-keys", "-t", target, "Enter")

    def test_send_raw_keys_mixed_ansi_and_text(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        mock_run = MagicMock(return_value=_make_completed())
        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux", mock_run):
            result = tmux.send_raw_keys("test_node", "ab\x1b[Bcd\n")
            assert result is True
            target = impl.agent_target("test_node")
            mock_run.assert_any_call("send-keys", "-l", "-t", target, "ab")
            mock_run.assert_any_call("send-keys", "-t", target, "Down")
            mock_run.assert_any_call("send-keys", "-l", "-t", target, "cd")
            mock_run.assert_any_call("send-keys", "-t", target, "Enter")

    def test_send_raw_keys_no_tmux(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        with patch.object(impl, "has_tmux", return_value=False):
            assert tmux.send_raw_keys("any", "hi") is False


class TestSendInitialPrompt:
    def test_agent_process_found(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux") as mock_tmux, \
             patch.object(impl, "send_keys") as mock_send_keys, \
             patch.object(impl, "time") as _:
            mock_send_keys.return_value = True
            mock_tmux.side_effect = [
                _make_completed(stdout="opencode\n"),
                _make_completed(stdout="> hello there\n"),
            ]

            _run_send_sync(tmux, "test_node", "do work")
            assert mock_send_keys.called

    def test_agent_never_appears(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux") as mock_tmux, \
             patch.object(impl, "send_keys") as mock_send_keys, \
             patch.object(impl, "time") as _:
            mock_send_keys.return_value = True
            mock_tmux.return_value = _make_completed(returncode=1)

            _run_send_sync(tmux, "test_node", "do work")
            assert mock_send_keys.called

    def test_exception_recovery(self):
        tmux = _real_tmux_module()
        from armada_ai.infrastructure import tmux_session as impl

        with patch.object(impl, "has_tmux", return_value=True), \
             patch.object(impl, "tmux") as mock_tmux, \
             patch.object(impl, "send_keys") as mock_send_keys, \
             patch.object(impl, "time") as _:
            mock_send_keys.return_value = True
            mock_tmux.side_effect = RuntimeError("broken")

            _run_send_sync(tmux, "test_node", "do work")
            assert mock_send_keys.called
