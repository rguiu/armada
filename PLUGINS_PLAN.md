# Armada — Plugin/Skill/Agent/Tool Management Plan

## Current State

Right now Armada spreads skill files across multiple locations:

| What | Global | Per-project |
|------|--------|-------------|
| OpenCode skills | `~/.config/opencode/skills/armada-*/SKILL.md` | `.opencode/skills/armada-*/SKILL.md` |
| Claude skills | `~/.claude/skills/armada-*/SKILL.md` | `.claude/skills/armada-*/SKILL.md` |
| Claude hooks | `~/.claude/hooks/*.sh` | `.claude/hooks/*.sh` |
| OpenCode plugins | `~/.config/opencode/plugins/armada-pending.{ts,js}` | `.opencode/plugins/armada-pending.{ts,js}` |
| Agent hook files | `~/.armada/hooks/{node}.md` | N/A |

Problems:
- Files are **copied**, not linked. Updates to global don't reach projects.
- `armada setup` + dashboard "Sync" button are needed to push changes.
- No project-specific overrides — all projects get the same skills.
- Adding a new skill/plugin requires modifying code in `tmux.py` + `server.py`.

## Proposed Architecture

### 1. Single source of truth: `~/.armada/bundles/`

All Armada-provided assets live in one directory tree:

```
~/.armada/
├── bundles/                    # versioned bundles
│   ├── opencode-skills/        # symlinked into agent config
│   │   ├── armada-node/
│   │   │   └── SKILL.md
│   │   ├── armada-worker/
│   │   │   └── SKILL.md
│   │   └── armada-orchestrator/
│   │       └── SKILL.md
│   ├── claude-skills/          # same structure for Claude
│   │   ├── armada-node/
│   │   ├── armada-worker/
│   │   └── armada-orchestrator/
│   ├── claude-hooks/
│   │   ├── pre-tool.sh
│   │   ├── post-tool.sh
│   │   ├── stop.sh
│   │   └── permission.sh
│   └── opencode-plugins/
│       ├── armada-pending.js
│       └── armada-pending.ts
│
├── config.yaml                 # global config
└── projects/
    └── {project-id}.yaml       # per-project overrides
```

### 2. Symlink strategy

**Global install** (`armada setup`):
```
~/.config/opencode/skills/armada-node   → ~/.armada/bundles/opencode-skills/armada-node
~/.config/opencode/skills/armada-worker  → ~/.armada/bundles/opencode-skills/armada-worker
~/.config/opencode/skills/armada-orchestrator → ~/.armada/bundles/opencode-skills/armada-orchestrator

~/.config/opencode/plugins/armada-pending.js  → ~/.armada/bundles/opencode-plugins/armada-pending.js
~/.config/opencode/plugins/armada-pending.ts  → ~/.armada/bundles/opencode-plugins/armada-pending.ts
```

**Per-project install** (when a project is registered):
```
my-project/.opencode/skills/armada-node   → ~/.armada/bundles/opencode-skills/armada-node
my-project/.opencode/skills/armada-worker  → ~/.armada/bundles/opencode-skills/armada-worker
```

**Per-project override** (if a project needs custom skills):
```
my-project/.opencode/skills/armada-node/SKILL.md   # real file, overrides symlink
```

### 3. Why symlinks instead of copying

| Approach | Updates | Disk usage | Project-specific |
|----------|---------|------------|------------------|
| Copy (current) | Re-sync needed | Duplicated | Manual per-project |
| Symlink (proposed) | Instant | One copy | Override with real file |

### 4. `armada` CLI — unified interface

```bash
# Global operations
armada skills list                          # list all available bundles
armada skills install                       # symlink bundles to global agent configs
armada skills update                        # pull latest bundles, relink

# Per-project operations
armada skills install --project my-api      # symlink bundles into my-api/.opencode/
armada skills list --project my-api         # show what's active for this project
armada skills add my-custom-skill.md --project my-api   # add a project-specific skill file

# Plugin management
armada plugins list
armada plugins enable pending-alert         # symlink a plugin globally
armada plugins enable pending-alert --project my-api   # per-project

# Hook management  
armada hooks list
armada hooks install
armada hooks install --project my-api
```

### 5. `armada.json` — project-level config

When a project is registered, a `.armada.json` is created in its root:

```json
{
  "version": 1,
  "project_id": "shipping-api",
  "skills": {
    "armada-node": true,
    "armada-worker": true,
    "armada-orchestrator": true
  },
  "plugins": {
    "armada-pending": true
  },
  "hooks": {
    "claude": true
  },
  "overrides": {
    "skills": {
      "armada-node": ".armada/custom-node/SKILL.md"
    }
  }
}
```

- `skills`, `plugins`, `hooks` — boolean flags to enable/disable specific bundles
- `overrides` — paths to project-specific override files (relative to project root)

### 6. Architecture on disk after setup

```
~/.armada/
├── bundles/                    # master copies (versioned, updated via git/curl)
│   └── ...
├── config.yaml                 # global: which bundles are enabled
└── projects/
    └── shipping-api.yaml       # per-project: overrides + enabled flags

~/projects/shipping-api/
├── .armada.json                # project config (committed to repo)
├── .opencode/
│   ├── skills/
│   │   ├── armada-node  → ~/.armada/bundles/opencode-skills/armada-node  (symlink)
│   │   ├── armada-worker → ~/.armada/bundles/opencode-skills/armada-worker (symlink)
│   │   └── custom-review/
│   │       └── SKILL.md        # project-specific skill (real file)
│   └── plugins/
│       └── armada-pending.js → ~/.armada/bundles/opencode-plugins/armada-pending.js
└── .claude/
    ├── skills/  →  (same symlink structure)
    └── hooks/
        ├── pre-tool.sh  → ~/.armada/bundles/claude-hooks/pre-tool.sh
        └── ...
```

### 7. Implementation phases

| Phase | What | Effort |
|-------|------|--------|
| **0** | Refactor `tmux.py` to read skill sources from a single `bundles/` dir instead of separate `skills/` + `hooks/` dirs in the repo | 2h |
| **1** | `armada setup` creates symlinks instead of copies. `armada skills install` command | 3h |
| **2** | `.armada.json` per-project config. Project registration writes it. Node creation reads it | 4h |
| **3** | Per-project overrides: if a real file exists at the symlink target, use it; otherwise symlink. `armada skills add` | 3h |
| **4** | `armada plugins list/enable/disable` and `armada hooks list/enable/disable` | 2h |
| **5** | Dashboard UI: per-project skill/plugin toggles in the project settings panel | 4h |
| **6** | Self-update: `armada skills update` pulls latest bundles from git/remote | 1 day |

### 8. Key design decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Symlinks vs copies | Symlinks for bundled; copies for overrides | Zero maintenance after setup, instant global updates |
| Config format | `.armada.json` (JSON) | Already used by OpenCode; familiar to devs |
| Bundle storage | `~/.armada/bundles/` | Single source of truth, easy to inspect/update |
| Per-project isolation | Symlink + real-file override | Standard filesystem pattern, no custom resolver needed |
| CLI surface | Subcommands: `skills`, `plugins`, `hooks` | Discoverable, follows `armada setup`/`armada token` pattern |
| Agent compatibility | Works with OpenCode + Claude Code | Maintain current dual-agent support |

### 9. Migration from current system

On first run of the new `armada setup`:
1. Detect existing copied skills in `~/.config/opencode/skills/` and `.opencode/skills/`
2. If they match the bundled version, replace with symlinks
3. If they differ (user modified), keep as-is and warn
4. Write `.armada.json` to each registered project

Existing projects continue working without changes — the symlink transition is transparent to the agent.

## Non-Overwrite Rule

**Armada skills must never overwrite project-owned files.**

When installing skills to a project:

```
For each bundle skill (e.g. armada-node):
  target = .opencode/skills/armada-node/SKILL.md
  if target exists AND is NOT a symlink to our bundle:
    SKIP — project has its own version
  elif target exists AND is a symlink to our bundle:
    UPDATE symlink to current bundle path
  else:
    CREATE symlink to bundle
```

This prevents:

| Scenario | Behavior |
|----------|----------|
| Project has no `armada-node` | Symlink created |
| Project has its own custom `armada-node` | Left untouched |
| Project has stale symlink from old Armada version | Updated to current bundle |
| Project has `armada-node` that happens to be identical to bundle | Left as-is, logged |

**Detecting "owned by project"**: any real file (not a symlink, or symlink pointing outside `~/.armada/bundles/`) is project-owned.

## Skills Listing in the Dashboard

The detail panel should show what skills a node has access to. Two levels:

### 1. Per-project — what's IN the project directory
```
GET /api/project-labels/:id/skills
→ {
  "opencode": {
    "path": "/Users/.../my-project/.opencode/skills",
    "skills": [
      {"name": "armada-node", "source": "armada", "path": ".opencode/skills/armada-node/SKILL.md"},
      {"name": "armada-worker", "source": "armada", "path": ".opencode/skills/armada-worker/SKILL.md"},
      {"name": "my-custom-review", "source": "project", "path": ".opencode/skills/my-custom-review/SKILL.md"}
    ]
  },
  "claude": { ... }
}
```

Source can be:
- `"armada"` — provided by Armada (symlink to bundle)
- `"project"` — project's own custom skill (real file or non-armada symlink)
- `"global"` — from `~/.config/opencode/skills/` (if no project-level override)

### 2. Per-node — what the node actually sees
```
GET /api/nodes/:id/skills
→ same structure, but resolved: if project has "my-custom-review" and global has "armada-node",
  the node sees both (project overrides global for same name).
```

### Dashboard UI

In the detail panel, below the activity log:

```
┌─ Skills ────────────────────────────┐
│ armada-node          (armada)       │
│ armada-worker        (armada)       │
│ armada-orchestrator  (armada)       │
│ my-custom-review     (project)  ✎   │
└─────────────────────────────────────┘
```

- Each skill shows its name and source badge
- Clicking a skill could show its SKILL.md contents in a popover
- Project-owned skills could have an edit icon

## Implementation

| Step | Effort |
|------|--------|
| API: `GET /api/project-labels/:id/skills` — read project `.opencode/skills/` and `.claude/skills/`, classify source | 1h |
| API: `GET /api/nodes/:id/skills` — same, but resolve per-node (fallback to global if no project) | 30m |
| Dashboard: skills list in detail panel | 1h |
| Symlink non-overwrite logic in `install_skills()` | 30m |
