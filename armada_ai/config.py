import os
import re

from . import constants

CONFIG_PATH = constants.CONFIG_PATH

DEFAULTS = {
    "port": int(os.environ.get("ARMADA_PORT", constants.DEFAULT_PORT)),
    "host": os.environ.get("ARMADA_HOST", constants.DEFAULT_HOST),
    "default_agent": "opencode",
    "health_interval": constants.DEFAULT_HEALTH_INTERVAL,
    "max_restarts": constants.MAX_RESTARTS,
    "project_roots": ["~/Projects", "~/projects", "~/code", "~/src", "~/work"],
}

_cache = None
_cache_mtime = 0


def _parse_yaml(text: str) -> dict:
    lines = text.splitlines()
    result = {}
    stack = [(-1, result)]

    def next_content(index: int) -> str:
        for line in lines[index + 1:]:
            if line.strip() and not line.strip().startswith("#"):
                return line
        return ""

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if stripped == "-":
            if isinstance(current, list):
                item = {}
                current.append(item)
                stack.append((indent, item))
            continue

        if stripped.startswith("- "):
            if isinstance(current, list):
                value_str = stripped[2:].strip()
                current.append(_parse_value(value_str.strip('"').strip("'")))
            continue

        if ": " in stripped:
            key, value_str = stripped.split(": ", 1)
            key = key.strip().strip('"').strip("'")
            value_str = value_str.strip().strip('"').strip("'")
            if isinstance(current, dict):
                current[key] = _parse_value(value_str)
            continue

        if stripped.endswith(":"):
            key = stripped[:-1].strip().strip('"').strip("'")
            following = next_content(index)
            following_indent = len(following) - len(following.lstrip())
            is_list = (following_indent > indent
                       and following.strip().startswith("-"))
            child = [] if is_list else {}
            if isinstance(current, dict):
                current[key] = child
            stack.append((indent, child))

    return result


def _parse_value(s: str):
    s_lower = s.lower()
    if s == "[]":
        return []
    if s == "{}":
        return {}
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
    os.makedirs(os.path.dirname(CONFIG_PATH), mode=0o700, exist_ok=True)
    lines = []
    for key, value in cfg.items():
        lines.extend(_yaml_lines(key, value, 0))
    with open(CONFIG_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
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
