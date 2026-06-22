"""Project label persistence and JSON sync."""
import json
import os
import sqlite3

from .. import constants
from ..domain.models import ProjectLabel
from .database import _get_conn, _retry, _ensure_dir


def add_project_label(id: str, name: str, path: str):
    def _do():
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO project_labels (id, name, path) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, path = excluded.path",
                (id, name, path),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            existing = conn.execute(
                "SELECT id FROM project_labels WHERE path = ? AND id != ?", (path, id)
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Path '{path}' is already registered as '{existing[0]}'. "
                    f"Remove it first."
                ) from e
            raise
    _retry(_do, write=True)
    _save_projects_to_json()


def delete_project_label(id: str):
    def _do():
        conn = _get_conn()
        conn.execute("DELETE FROM project_labels WHERE id = ?", (id,))
        conn.commit()
    _retry(_do, write=True)
    _save_projects_to_json()


def list_project_labels() -> list[ProjectLabel]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, path FROM project_labels ORDER BY name"
    ).fetchall()
    return [ProjectLabel(id=r[0], name=r[1], path=r[2]) for r in rows]


def get_project_label_path(label_id: str) -> str | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT path FROM project_labels WHERE id = ?", (label_id,)
    ).fetchone()
    return row[0] if row else None


# --- JSON persistence ---

def _save_projects_to_json():
    labels = list_project_labels()
    _ensure_dir()
    with open(constants.PROJECTS_FILE, "w") as f:
        json.dump([{"id": lb.id, "name": lb.name, "path": lb.path}
                    for lb in labels], f, indent=2)


def sync_projects_from_json():
    if not os.path.exists(constants.PROJECTS_FILE):
        _save_projects_to_json()
        return

    try:
        with open(constants.PROJECTS_FILE) as f:
            json_projects = json.load(f)
    except (json.JSONDecodeError, IOError):
        _save_projects_to_json()
        return

    db_projects = {p.id: p for p in list_project_labels()}

    for jp in json_projects:
        if not isinstance(jp, dict):
            continue
        if jp["id"] not in db_projects:
            add_project_label(jp["id"], jp["name"], jp["path"])
            continue
        db_p = db_projects[jp["id"]]
        if jp["name"] != db_p.name or jp["path"] != db_p.path:
            add_project_label(jp["id"], jp["name"], jp["path"])
            continue

    db_ids = {p.id for p in db_projects.values()}
    json_ids = {p["id"] for p in json_projects if isinstance(p, dict)}
    if db_ids != json_ids:
        _save_projects_to_json()
