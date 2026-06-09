import time

from . import db
from . import tmux
from . import logs


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
