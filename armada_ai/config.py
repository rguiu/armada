import os
import re

from . import constants

CONFIG_PATH = constants.CONFIG_PATH

DEFAULTS = {
    "port": constants.DEFAULT_PORT,
    "host": constants.DEFAULT_HOST,
    "default_agent": "opencode",
    "health_interval": constants.DEFAULT_HEALTH_INTERVAL,
    "max_restarts": constants.MAX_RESTARTS,
    "projects": [],
}

_cache = None
_cache_mtime = 0


def _parse_yaml(text: str) -> dict:
    result = {}
    stack = [(result, -1)]
    pending_list_key = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        while len(stack) > 1 and stack[-1][1] >= indent:
            stack.pop()

        current = stack[-1][0]

        if stripped.startswith("- "):
            value_str = stripped[2:].strip()
            value = _parse_value(value_str.strip('"').strip("'"))
            if isinstance(current, list):
                current.append(value)
            elif pending_list_key:
                if not isinstance(result[pending_list_key], list):
                    result[pending_list_key] = []
                result[pending_list_key].append(value)
        elif ": " in stripped:
            key, value_str = stripped.split(": ", 1)
            key = key.strip().strip('"').strip("'")
            value_str = value_str.strip().strip('"').strip("'")
            value = _parse_value(value_str)
            if isinstance(current, dict):
                current[key] = value
            else:
                result[key] = value
            pending_list_key = None
        elif stripped.endswith(":"):
            key = stripped[:-1].strip().strip('"').strip("'")
            current[key] = {}
            stack.append((current[key], indent))
        elif stripped == "-":
            if isinstance(current, dict):
                for k in current:
                    if not isinstance(current[k], list):
                        current[k] = []
                    pending_list_key = k
                    break

    return result


def _parse_value(s: str):
    s_lower = s.lower()
    if s_lower == "true":
        return True
    if s_lower == "false":
        return False
    if s_lower == "null" or s_lower == "~":
        return None
    if re.match(r'^-?\d+$', s):
        return int(s)
    if re.match(r'^-?\d+\.\d+$', s):
        return float(s)
    return s


def _load_config(force: bool = False) -> dict:
    global _cache, _cache_mtime
    if not force and _cache is not None:
        try:
            mtime = os.path.getmtime(CONFIG_PATH)
            if mtime <= _cache_mtime:
                return _cache
        except OSError:
            return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH) as f:
            text = f.read()
        cfg = _parse_yaml(text)
        for key, default in DEFAULTS.items():
            if key not in cfg:
                cfg[key] = default
        _cache = cfg
        _cache_mtime = os.path.getmtime(CONFIG_PATH)
        return cfg
    except FileNotFoundError:
        _cache = dict(DEFAULTS)
        _cache_mtime = 0
        return _cache
    except Exception:
        return dict(DEFAULTS)


def get(key: str):
    cfg = _load_config()
    return cfg.get(key, DEFAULTS.get(key))


def get_all() -> dict:
    return dict(_load_config())


def write_config(cfg: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    lines = []
    for key, value in cfg.items():
        lines.extend(_yaml_lines(key, value, 0))
    with open(CONFIG_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    global _cache, _cache_mtime
    _cache = dict(cfg)
    try:
        _cache_mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        _cache_mtime = 0


def _yaml_lines(key: str, value, indent: int) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines = [f"{prefix}{key}:"]
        for k, v in value.items():
            lines.extend(_yaml_lines(k, v, indent + 2))
        return lines
    elif isinstance(value, list):
        if not value:
            return [f"{prefix}{key}: []"]
        lines = [f"{prefix}{key}:"]
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}  -")
                for k, v in item.items():
                    lines.extend(_yaml_lines(k, v, indent + 4))
            else:
                lines.append(f"{prefix}  - {_yaml_value(item)}")
        return lines
    elif isinstance(value, bool):
        return [f"{prefix}{key}: {'true' if value else 'false'}"]
    elif isinstance(value, (int, float)):
        return [f"{prefix}{key}: {value}"]
    elif value is None:
        return [f"{prefix}{key}: null"]
    else:
        val_str = str(value)
        if any(c in val_str for c in ": #{}[]&*!|>'\"%@`"):
            val_str = '"' + val_str.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return [f"{prefix}{key}: {val_str}"]


def _yaml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    val_str = str(value)
    if any(c in val_str for c in ": #{}[]&*!|>'\"%@`"):
        return '"' + val_str.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return val_str


def init_config():
    if not os.path.exists(CONFIG_PATH):
        write_config(DEFAULTS)
