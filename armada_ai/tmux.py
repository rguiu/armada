"""Tmux operations — re-exports from infrastructure modules for backward compatibility."""
import threading as _threading  # noqa: F401  used by tests
import time as _time            # noqa: F401  used by tests

from .infrastructure.tmux_session import (  # noqa: F401  re-exported
    ARMADA_SESSION,
    agent_session, agent_target, agent_workspace,
    has_tmux, tmux,
    ensure_armada_session, create_node_window, kill_node_window,
    capture_pane_content, window_exists, running_window_names,
    send_keys, send_raw_keys, send_initial_prompt,
    cleanup_stale_sessions,
)
from .infrastructure.deployment import (  # noqa: F401  re-exported
    install_skills_to_project as install_skills,
    install_skills_to_user as install_user_skills,
    save_agent_hook,
    agent_hook_instructions,
    deploy_for_agent_type,
    deploy_claude_hooks,
)
from .infrastructure.terminal_attach import (  # noqa: F401  re-exported
    attach_to_node as attach_node,
)
from .project_explorer import (  # noqa: F401  re-exported
    list_project_skills,
    list_project_plugins,
    list_project_hooks,
    get_project_config,
    get_project_git_info,
)

# Backward-compatible private aliases (used by test_tmux.py)
_has_tmux = has_tmux
_tmux = tmux
_agent_target = agent_target
_agent_session = agent_session
_agent_workspace = agent_workspace
_deploy_claude_hooks = deploy_claude_hooks
threading = _threading
time = _time
