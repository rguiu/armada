import threading
import time

from . import db
from . import tmux


def start_health_loop(interval: int = 15):
    """Start a background thread that checks node health periodically."""

    def check():
        while True:
            time.sleep(interval)
            try:
                _run_health_check()
            except Exception:
                pass

    thread = threading.Thread(target=check, daemon=True)
    thread.start()


def _run_health_check():
    nodes = db.get_all_nodes(include_dead=False)
    running_windows = tmux.running_window_names()

    for node in nodes:
        name = node["name"]
        if name not in running_windows:
            _mark_node_dead(node["id"])


def _mark_node_dead(node_id: int):
    dead = db.kill_node(node_id)
    for entry in dead:
        try:
            tmux.kill_node_window(entry["name"])
        except Exception:
            pass
