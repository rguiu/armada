"""Seed a demo database for screen recordings. Creates schema + project labels only (no nodes)."""

import datetime
import json
import os
import sqlite3
import sys

from . import constants

DEMO_PROJECTS = [
    {"id": "nano-vllm", "name": "nano-vLLM", "path": "/Users/armada/Projects/nano-vllm"},
    {"id": "sglang", "name": "SGLang", "path": "/Users/armada/Projects/sglang"},
    {"id": "vllm", "name": "vLLM", "path": "/Users/armada/Projects/vllm"},
    {"id": "armada", "name": "Armada", "path": "/Users/armada/Projects/armadaai"},
    {"id": "pglease", "name": "PGLease", "path": "/Users/armada/Projects/pglease"},
]


def _ensure_dir(path: str):
    dirname = os.path.dirname(path) if not os.path.isdir(path) else path
    if dirname:
        os.makedirs(dirname, exist_ok=True)


def _seed_database(db_path: str):
    if os.path.exists(db_path):
        backup = db_path + ".backup-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        try:
            os.rename(db_path, backup)
            print(f"  Existing DB backed up to: {backup}")
        except OSError:
            pass

    _ensure_dir(os.path.dirname(db_path))
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS project_labels (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
            project_label_id TEXT REFERENCES project_labels(id),
            tmux_pane_id TEXT,
            tmux_session_id TEXT,
            colour TEXT NOT NULL,
            status TEXT DEFAULT 'idle',
            agent_type TEXT DEFAULT 'auto',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            killed_at TEXT,
            hidden_at TEXT,
            total_tokens_in INTEGER DEFAULT 0,
            total_tokens_out INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS status_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            message TEXT,
            options TEXT DEFAULT '',
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS hourly_stats (
            hour TEXT PRIMARY KEY,
            active_agents INTEGER NOT NULL DEFAULT 0,
            total_agents INTEGER NOT NULL DEFAULT 0,
            total_cost REAL NOT NULL DEFAULT 0.0,
            total_tokens_in INTEGER NOT NULL DEFAULT 0,
            total_tokens_out INTEGER NOT NULL DEFAULT 0,
            snapshot_ts TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_reports_node
            ON status_reports(node_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_killed ON nodes(killed_at);
        CREATE INDEX IF NOT EXISTS idx_nodes_hidden ON nodes(hidden_at);
        CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project_label_id);
    """)
    conn.commit()

    for proj in DEMO_PROJECTS:
        _ensure_dir(proj["path"])
        conn.execute(
            "INSERT OR REPLACE INTO project_labels (id, name, path) VALUES (?, ?, ?)",
            (proj["id"], proj["name"], proj["path"]),
        )
    conn.commit()
    conn.close()

    projects_path = os.path.join(constants.DATA_DIR, "projects.json")
    try:
        with open(projects_path, "w") as f:
            json.dump(DEMO_PROJECTS, f, indent=2)
    except OSError:
        pass

    print()
    print(f"  Projects:   {len(DEMO_PROJECTS)}")
    print("  Nodes:      0 (empty — ready for your demo)")
    print()
    print(f"  Database:   {db_path}")
    print()
    print("  Start with:")
    print(f"    ARMADA_DB_PATH={db_path} armada start")


def seed(force: bool = False) -> None:
    db_path = constants.DB_PATH

    if not db_path.endswith("-demo.db") and not force:
        print(
            "Refusing to seed a non-demo database.\n"
            "Use ARMADA_DB_PATH to point to a demo path:\n\n"
            "  ARMADA_DB_PATH=~/.armada/armada-demo.db armada demodb seed\n\n"
            "Or override with --force: armada demodb seed --force",
            file=sys.stderr,
        )
        sys.exit(1)

    _seed_database(db_path)
