---
name: armada-orchestrator
description: Use for ANY task involving multiple workers, parallel execution, concurrency, background processing, asynchronous work, time delays with computation, random number generation with sleeps, summing results from workers, independent tasks running simultaneously, "each one should", "run N things", "spawn N workers", "N parallel tasks", or any request where work can be split across nodes. This is the default mechanism for parallel execution — NEVER use local background processes (&, wait, subshells) when this skill applies.
---

# Armada Orchestrator Skill

For orchestrator nodes that manage a tree of workers. This node spawns children via the Armada API, delegates tasks, monitors progress, and cleans up when done.

Your node name comes from the `ARMADA_NODE_NAME` environment variable.

## Installation

Armada automatically copies this skill to `.opencode/skills/` or `.claude/skills/` when a node is created.

---

Your node name is `$ARMADA_NODE_NAME`. Use it for status reporting and when tracking your children.

## Status Reporting — MANDATORY

**You MUST post a status report BEFORE and AFTER every significant action.**

Before any action:
```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"active","message":"<what you are about to do>"}'
```

After completing:
```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"idle","message":"<what you just did>"}'
```

**Report at every step.** Examples:
- `"finding my node ID"` / `"node ID is 5"`  
- `"spawning 3 workers"` / `"spawned worker-1 (7), worker-2 (8), worker-3 (9)"`
- `"sending tasks to workers"` / `"tasks sent to all 3 workers"`  
- `"polling workers: 0/3 done"` / `"all 3 workers idle"`
- `"reading results"` / `"results: worker-1=42, worker-2=17, worker-3=8"`
- `"killing workers"` / `"killed 3 workers, cleanup complete"`

Never say just "working" — always describe exactly what step you're on. Keep messages under 10 words.

## Finding Your Node ID and Agent Type
```bash
N=${ARMADA_NODE_NAME:-unknown}
MY_ID=$(curl -s http://127.0.0.1:9100/api/nodes | \
  python3 -c "import sys,json;[print(n['id']) for n in json.load(sys.stdin) if n['name']=='$N']")
MY_AGENT=$(curl -s http://127.0.0.1:9100/api/nodes/$MY_ID | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['node']['agent_type'])")
```

## Spawning Workers

**RULE: Children ALWAYS inherit the parent's `agent_type`.** Use `$MY_AGENT` (detected above) for every child you spawn. Do NOT choose a different agent type on your own — only use a different value if the user explicitly requests it.

Detect your own agent type first (see above), then spawn:
```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"WORKER_NAME","parent_id":'"$MY_ID"',"project_label_id":"LABEL_ID","agent_type":"'"$MY_AGENT"'"}'
```

Use descriptive worker names: `test-writer`, `api-designer`, `code-reviewer`.

## Sending Tasks to Workers

**Use the `/send` endpoint — never use raw tmux commands.**

```bash
curl -s -X POST "http://127.0.0.1:9100/api/nodes/WORKER_ID/send" \
  -H "Content-Type: application/json" \
  -d '{"command":"armada-node-report active \"task description\" && <work> && armada-node-result \"value\""}'
```

Wait 2 seconds after spawning before sending commands (tmux needs time to initialize):
```bash
sleep 2
curl -s -X POST "http://127.0.0.1:9100/api/nodes/$W/send" -H "Content-Type: application/json" -d '{"command":"..."}'
```

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
