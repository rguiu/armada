"""Project exploration: scanning skills, plugins, hooks, configs, and git info.

Extracted from tmux.py — these are read-only inspection functions,
not tmux operations.
"""
import json
import os
import re
import subprocess
from pathlib import Path


_ANSI_RE = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'
    r'|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)'
    r'|\x1b[()][0-9A-Z]'
    r'|\x1b[>=]'
)
_SENSITIVE_KEY_RE = re.compile(r"(token|key|secret|auth|password)", re.IGNORECASE)


def _skill_description(skill_md: Path) -> str:
    try:
        for line in skill_md.read_text().split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and len(stripped) > 5:
                return stripped[:120]
    except Exception:
        pass
    return ""


def _scan_skills_dir(skills_dir: Path, project_path: str, bundles_dir: str) -> list[dict]:
    skills = []
    if not skills_dir.is_dir():
        return skills
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        if entry.is_symlink():
            try:
                target = str(entry.resolve())
            except Exception:
                target = ""
            source = "armada" if bundles_dir in target else "project"
        else:
            source = "project"
        skills.append({
            "name": entry.name,
            "source": source,
            "path": str(skill_md.relative_to(project_path)) if project_path else str(skill_md),
            "description": _skill_description(skill_md),
        })
    return skills


def list_project_skills(project_path: str) -> dict:
    bundles_dir = os.path.expanduser("~/.armada/bundles")
    home = Path.home()
    global_dirs = {
        "opencode": home / ".config" / "opencode" / "skills",
        "claude": home / ".claude" / "skills",
    }

    by_name = {}
    project_path_str = project_path

    for agent in ("opencode", "claude"):
        project_skills_dir = Path(project_path) / f".{agent}" / "skills"
        global_skills_dir = global_dirs[agent]

        for skill in _scan_skills_dir(project_skills_dir, project_path_str, bundles_dir):
            name = skill["name"]
            if name not in by_name:
                by_name[name] = skill

        for skill in _scan_skills_dir(global_skills_dir, str(home), bundles_dir):
            name = skill["name"]
            if name not in by_name:
                skill = dict(skill)
                skill["source"] = "global"
                by_name[name] = skill

    skills = sorted(
        by_name.values(),
        key=lambda s: ({"armada": 0, "project": 1, "global": 2}[s["source"]], s["name"]),
    )
    return {"skills": skills}


def list_project_plugins(project_path: str) -> dict:
    plugins = []
    project = Path(project_path)

    agent_dirs = [
        ("opencode", project / ".opencode" / "plugin"),
        ("opencode", project / ".opencode" / "plugins"),
        ("claude", project / ".claude" / "plugins"),
    ]

    seen = set()
    for agent, d in agent_dirs:
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file() and f.name not in seen:
                    seen.add(f.name)
                    plugins.append({"name": f.name, "agent": agent})

    return {"plugins": plugins}


def list_project_hooks(project_path: str) -> dict:
    hooks = []
    project = Path(project_path)

    for agent, d in [
        ("claude", project / ".claude" / "hooks"),
        ("opencode", project / ".opencode" / "hooks"),
    ]:
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    hooks.append({"name": f.name, "agent": agent})

    return {"hooks": hooks}


def _redact_config(obj):
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if _SENSITIVE_KEY_RE.search(k) and isinstance(v, str) and len(v) > 4:
                result[k] = v[:4] + "***"
            else:
                result[k] = _redact_config(v)
        return result
    if isinstance(obj, list):
        return [_redact_config(item) for item in obj]
    return obj


def get_project_config(project_path: str) -> dict:
    project = Path(project_path)
    home = Path.home()
    configs = {}

    for candidate in [
        project / "opencode.json",
        project / "opencode.jsonc",
        project / ".opencode" / "opencode.json",
        project / ".opencode" / "opencode.jsonc",
    ]:
        if candidate.is_file():
            try:
                raw = candidate.read_text()
                cleaned = re.sub(r"//.*?\n|/\*.*?\*/", "", raw, flags=re.DOTALL)
                configs["opencode"] = _redact_config(json.loads(cleaned))
            except Exception:
                configs["opencode"] = {"_error": f"Could not parse {candidate.name}"}
            break

    if "opencode" not in configs:
        global_oc = home / ".config" / "opencode" / "opencode.jsonc"
        if global_oc.is_file():
            try:
                raw = global_oc.read_text()
                cleaned = re.sub(r"//.*?\n|/\*.*?\*/", "", raw, flags=re.DOTALL)
                configs["opencode"] = _redact_config(json.loads(cleaned))
            except Exception:
                pass

    for candidate in [project / ".claude" / "settings.json", home / ".claude" / "settings.json"]:
        if candidate.is_file():
            try:
                configs["claude"] = _redact_config(json.loads(candidate.read_text()))
            except Exception:
                configs["claude"] = {"_error": "Could not parse settings.json"}
            break

    return {"configs": configs}


def get_project_git_info(project_path: str) -> dict:
    info = {}

    for key, args in [
        ("branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        ("remote", ["git", "remote", "get-url", "origin"]),
        ("last_commit", ["git", "log", "-1", "--format=%h %s", "--abbrev=8"]),
    ]:
        try:
            r = subprocess.run(
                args, capture_output=True, text=True, cwd=project_path, timeout=5,
            )
            info[key] = r.stdout.strip()
        except Exception:
            info[key] = ""

    return {"git": info}
