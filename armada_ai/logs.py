import os
import json
import time
import gzip
import threading

from . import constants

LOGS_DIR = constants.LOGS_DIR
_write_lock = threading.Lock()

LOG_LEVELS = ("debug", "info", "warn", "error")


def _ensure_dir():
    os.makedirs(LOGS_DIR, exist_ok=True)


def log_event(node_name: str, event_type: str, data: dict | None = None,
              level: str = "info"):
    _ensure_dir()
    entry = {
        "ts": time.time(),
        "type": event_type,
        "name": node_name,
        "level": level,
    }
    if data:
        entry["data"] = data

    line = json.dumps(entry, ensure_ascii=False) + "\n"
    log_path = os.path.join(LOGS_DIR, f"{node_name}.jsonl")

    with _write_lock:
        with open(log_path, "a") as f:
            f.write(line)


def search_logs(query: str, limit: int = 50, node_name: str | None = None) -> list[dict]:
    _ensure_dir()
    results = []
    q_lower = query.lower()

    files = [f for f in os.listdir(LOGS_DIR) if f.endswith(".jsonl")]
    if node_name:
        target = f"{node_name}.jsonl"
        files = [f for f in files if f == target]

    for filename in sorted(files, reverse=True):
        if len(results) >= limit:
            break
        filepath = os.path.join(LOGS_DIR, filename)
        try:
            with open(filepath) as f:
                lines = f.readlines()
            for line in reversed(lines):
                if len(results) >= limit:
                    break
                if q_lower in line.lower():
                    try:
                        entry = json.loads(line)
                        results.append(entry)
                    except json.JSONDecodeError:
                        pass
        except (IOError, OSError):
            pass

    return results


def get_node_logs(node_name: str, limit: int = 50, before_ts: float | None = None) -> list[dict]:
    _ensure_dir()
    log_path = os.path.join(LOGS_DIR, f"{node_name}.jsonl")
    log_real = os.path.realpath(log_path)
    if not log_real.startswith(os.path.realpath(LOGS_DIR) + os.sep):
        return []
    if not os.path.exists(log_path):
        return []

    results = []
    try:
        with open(log_path) as f:
            lines = f.readlines()
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if before_ts and entry.get("ts", 0) >= before_ts:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
    except (IOError, OSError):
        pass

    return results


def rotate_logs(max_size_mb: int = 50):
    _ensure_dir()
    for filename in os.listdir(LOGS_DIR):
        if not filename.endswith(".jsonl"):
            continue
        filepath = os.path.join(LOGS_DIR, filename)
        try:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            if size_mb > max_size_mb:
                gz_path = filepath + ".gz"
                with open(filepath, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        f_out.writelines(f_in)
                os.remove(filepath)
        except (IOError, OSError):
            pass


def cleanup_old_rotated_logs(max_age_days: int = 30):
    _ensure_dir()
    now = time.time()
    cutoff = now - (max_age_days * 86400)
    for filename in os.listdir(LOGS_DIR):
        if not filename.endswith(".jsonl.gz"):
            continue
        filepath = os.path.join(LOGS_DIR, filename)
        try:
            if os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
        except (IOError, OSError):
            pass


def log_report(node_name: str, status: str, message: str | None):
    log_event(node_name, "report", {"status": status, "message": message}, level="info")


def log_create(node_name: str, agent_type: str, project: str | None):
    log_event(node_name, "create", {"agent_type": agent_type, "project": project}, level="info")


def log_kill(node_name: str):
    log_event(node_name, "kill", {}, level="warn")


def log_send(node_name: str, command: str):
    log_event(node_name, "send", {"command": command[:200]}, level="debug")


def log_attach(node_name: str):
    log_event(node_name, "attach", {}, level="info")


def log_health(node_name: str, dead: bool):
    log_event(node_name, "health", {"dead": dead}, level="warn")


def log_recover(node_name: str):
    log_event(node_name, "recover", {}, level="info")


def log_ws_connect(client_id: str, path: str):
    log_event("_server", "ws_connect", {"client": client_id, "path": path}, level="debug")


def log_ws_disconnect(client_id: str, path: str, reason: str = ""):
    log_event("_server", "ws_disconnect", {"client": client_id, "path": path, "reason": reason}, level="info")


def log_http_error(method: str, path: str, status: int, detail: str = ""):
    level = "error" if status >= 500 else "warn"
    log_event("_server", "http_error", {"method": method, "path": path, "status": status, "detail": detail[:200]}, level=level)


def log_server_start():
    _ensure_dir()
    log_path = os.path.join(LOGS_DIR, "_server.jsonl")
    with _write_lock:
        with open(log_path, "a") as f:
            json.dump({"ts": time.time(), "type": "server_start", "level": "info"}, f, ensure_ascii=False)
            f.write("\n")


def log_server_stop():
    _ensure_dir()
    log_path = os.path.join(LOGS_DIR, "_server.jsonl")
    with _write_lock:
        with open(log_path, "a") as f:
            json.dump({"ts": time.time(), "type": "server_stop", "level": "info"}, f, ensure_ascii=False)
            f.write("\n")


def log_agent_output(node_name: str, content: str):
    log_event(node_name, "output", {"content": content[:2000]}, level="debug")
