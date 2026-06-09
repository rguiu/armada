import time
import os

from . import db
from . import tmux
from . import logs


_MAX_RESTARTS = 3


def start_health_loop(interval: int = 15):
    _tick = 0

    def check():
        nonlocal _tick
        while True:
            time.sleep(interval)
            _tick += 1
            try:
                _run_health_check()
            except Exception:
                pass
            if _tick % 20 == 0:
                try:
                    db.prune_all_old_reports()
                    db.vacuum_db()
                except Exception:
                    pass

    import threading
    thread = threading.Thread(target=check, daemon=True)
    thread.start()


def recover_on_startup():
    running = tmux.running_window_names()
    if not running:
        return []

    live = db.recover_live_nodes(running)
    recovered = []
    for node in live:
        name = node["name"]
        if name not in running:
            continue
        logs.log_recover(name)
        db.add_status_report(node["id"], "idle", "server restarted — reconnected to tmux window")
        recovered.append(node)

    db.recover_nodes(running)
    return recovered


def _run_health_check():
    nodes = db.get_all_nodes(include_dead=False)
    running_windows = tmux.running_window_names()

    for node in nodes:
        name = node["name"]
        if name not in running_windows:
            logs.log_health(name, dead=True)
            _mark_node_dead(node["id"])
            _auto_restart_node(
                name=name,
                colour=node["colour"],
                agent_type=node["agent_type"],
                project_label_id=node["project_label_id"],
                working_dir=db.get_project_label_path(node["project_label_id"]) or os.getcwd(),
            )


def _mark_node_dead(node_id: int):
    dead = db.kill_node(node_id)
    for entry in dead:
        name = entry["name"]
        try:
            content = tmux.capture_pane_content(name)
            if content:
                logs.log_agent_output(name, content)
        except Exception:
            pass
        try:
            tmux.kill_node_window(name)
        except Exception:
            pass


def _auto_restart_node(name: str, colour: str, agent_type: str,
                        project_label_id: str, working_dir: str):
    restart_count = db.get_restart_count_for_name(name)
    if restart_count >= _MAX_RESTARTS:
        logs.log_event(name, "restart_limit", {"count": restart_count}, level="error")
        return

    try:
        pane_id = tmux.create_node_window(
            name=name, colour=colour,
            working_dir=working_dir, agent_type=agent_type,
        )
        if pane_id:
            node_id = db.create_node(
                name=name, colour=colour,
                parent_id=None,
                project_label_id=project_label_id,
                tmux_pane_id=pane_id, agent_type=agent_type,
            )
            db.add_status_report(node_id, "active",
                f"auto-restarted (attempt {restart_count + 1}/{_MAX_RESTARTS})")
            db.increment_restart_count(name)
            logs.log_event(name, "restarted", {
                "attempt": restart_count + 1,
                "agent_type": agent_type,
            }, level="warn")
    except Exception as e:
        logs.log_event(name, "restart_failed", {"error": str(e)}, level="error")
