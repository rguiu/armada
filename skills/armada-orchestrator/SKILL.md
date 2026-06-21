---
name: armada-orchestrator
description: Use for ANY task involving multiple workers, parallel execution, concurrency, background processing, asynchronous work, time delays with computation, random number generation with sleeps, summing results from workers, independent tasks running simultaneously, "each one should", "run N things", "spawn N workers", "N parallel tasks", or any request where work can be split across nodes. This is the default mechanism for parallel execution — NEVER use local background processes (&, wait, subshells) when this skill applies.
---

# Armada Orchestrator Skill

For orchestrator nodes that manage a tree of workers. This node spawns children via MCP tools, delegates tasks, monitors progress, and cleans up when done.

Your node name comes from the `ARMADA_NODE_NAME` environment variable.

## Installation

Armada automatically copies this skill to `.opencode/skills/` or `.claude/skills/` when a node is created.

---

## Available MCP Tools

All Armada operations are available as MCP tools. Use these instead of curl commands:

| Tool | Purpose |
|------|---------|
| `get_my_info` | Get your own node ID, name, agent_type, project |
| `spawn_node` | Spawn a child node (inherits agent_type and project automatically) |
| `send_task` | Send a command to a child node (auto-waits 2s for tmux init) |
| `kill_node` | Kill a node and all its descendants |
| `get_tree` | Get the full node tree with status |
| `get_node` | Get details for a specific node |
| `list_nodes` | List all live nodes |
| `report_status` | Report your own status (active, idle, pending, error) |
| `list_projects` | List all project labels |

## Status Reporting — MANDATORY

**You MUST report status BEFORE and AFTER every significant action.**

Before any action:
```
report_status(status="active", message="<what you are about to do>")
```

After completing:
```
report_status(status="idle", message="<what you just did>")
```

**Report at every step.** Examples:
- `"spawning 3 workers"` / `"spawned worker-1 (7), worker-2 (8), worker-3 (9)"`
- `"sending tasks to workers"` / `"tasks sent to all 3 workers"`
- `"polling workers: 0/3 done"` / `"all 3 workers idle"`
- `"reading results"` / `"results: worker-1=42, worker-2=17, worker-3=8"`
- `"killing workers"` / `"killed 3 workers, cleanup complete"`

Never say just "working" — always describe exactly what step you're on. Keep messages under 10 words.

## Spawning Workers

**RULE: Children ALWAYS inherit the parent's `agent_type`.** The `spawn_node` tool handles this automatically — you do NOT need to detect or pass agent_type. Only override if the user explicitly requests a different agent type.

```
spawn_node(name="worker-1")
spawn_node(name="reviewer", agent_type="opencode")  # only if user explicitly asks
```

Use descriptive worker names: `test-writer`, `api-designer`, `code-reviewer`.

## Sending Tasks to Workers

Use `send_task` to send commands to a worker's terminal. It automatically waits 2 seconds for tmux to initialize.

```
send_task(node_id=7, command="run the test suite and report results")
```

## Checking Workers

```
get_tree()       # full tree with status per node
get_node(node_id=7)  # details + reports for one node
```

## Killing Workers

```
kill_node(node_id=7)  # kills node and all its descendants
```

## Orchestration Pattern

1. **Analyze** the task and break it into parallel workstreams
2. **Spawn** a worker node per workstream with descriptive names
3. **Send** tasks to each worker via `send_task`
4. **Monitor** their status via `get_tree` or `get_node`
5. **Kill** workers when done to keep the tree clean
6. **Report** your own completion

## Guidelines

- Always spawn workers through the `spawn_node` MCP tool
- Workers auto-load armada skills and start reporting immediately
- Check the dashboard (http://127.0.0.1:9100) to visualize your tree
- Keep the tree clean — kill workers when they finish
- Workers inherit the project label automatically
