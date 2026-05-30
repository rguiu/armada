# Armada Orchestrator Skill

For orchestrator nodes that manage a tree of workers. This node spawns children via the Armada API, delegates tasks, monitors progress, and cleans up when done.

Your node name comes from the `ARMADA_NODE_NAME` environment variable.

## Installation

Armada automatically copies this skill to `.opencode/skills/` or `.claude/skills/` when a node is created.

---

Your node name is `$ARMADA_NODE_NAME`. Use it for status reporting and when tracking your children.

## Status Reporting

Report active status at the start of every response:
```bash
N=${ARMADA_NODE_NAME:-unknown}
MESSAGE="<5-word summary>"
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"active","message":"'"$MESSAGE"'"}'
```

Report idle at the end:
```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"idle","message":""}'
```

## Finding Your Node ID
```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s http://127.0.0.1:9100/api/nodes | \
  python3 -c "import sys,json;[print(n['id']) for n in json.load(sys.stdin) if n['name']=='$N']"
```

## Spawning Workers

Create a worker node (child) with the armada-worker or armada-node skill loaded:
```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"WORKER_NAME","parent_id":PARENT_ID,"project_label_id":"LABEL_ID","agent_type":"opencode"}'
```

Use descriptive worker names: `test-writer`, `api-designer`, `code-reviewer`.

The child node auto-starts with Armada skills installed and `ARMADA_NODE_NAME` set. The child will begin reporting status immediately.

## Checking Workers

```bash
curl -s http://127.0.0.1:9100/api/tree
```
Shows the full tree with status and latest message per node.

```bash
curl -s http://127.0.0.1:9100/api/nodes/CHILD_ID
```
Shows the worker's full activity log.

## Killing Workers

```bash
curl -s -X DELETE http://127.0.0.1:9100/api/nodes/CHILD_ID
```
Kills the worker and its descendants (cascade).

## Orchestration Pattern

1. **Analyze** the task and break it into parallel workstreams
2. **Spawn** a worker node per workstream with descriptive names
3. **Monitor** their status via the tree endpoint or dashboard
4. **Collect** results by having workers write output files
5. **Kill** workers when done to keep the tree clean
6. **Report** your own completion

## Guidelines

- Always spawn workers through the Armada API: `POST /api/nodes`
- Workers auto-load armada skills and start reporting immediately
- Check the dashboard (http://127.0.0.1:9100) to visualize your tree
- Keep the tree clean — kill workers when they finish
- Workers inherit the project label; ensure skills are installed there
