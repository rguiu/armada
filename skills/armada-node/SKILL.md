---
name: armada-node
description: Use when ARMADA_NODE_NAME environment variable is set (running inside an Armada tmux window). Also use when the user wants to spawn parallel workers, delegate tasks concurrently, run multiple things at once, do background computation, split work across nodes, sum results from workers, or farm out tasks. This skill teaches mandatory per-step status reporting AND spawning/managing child nodes via the Armada API.
---

# Armada Node Skill

This skill equips an agent to act as a managed node in an Armada cluster. The agent reports its status on every turn and can spawn child nodes.

The agent discovers its node name from the `ARMADA_NODE_NAME` environment variable, which is set automatically when the tmux window is created.

## Installation

Armada automatically copies this skill to `.opencode/skills/` or `.claude/skills/` when a node is created. No manual steps needed.

## Prerequisites

The Armada server must be running at `http://127.0.0.1:9100`. Start it with:

```bash
armada start
```

---

Your node name is available in the `ARMADA_NODE_NAME` environment variable. Use it in all status reports.

## Status Reporting — MANDATORY

**You MUST post a status report BEFORE and AFTER every significant action.** This is not optional. Your activity log is the primary way the Armada dashboard monitors you. A silent node looks dead.

### Before every action (mark yourself active):

```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"active","message":"<what you are about to do>"}'
```

### After every action (mark yourself idle with results):

```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"idle","message":"<what you just did>"}'
```

### When waiting for user input (mark yourself pending):

The Armada pending plugin handles permission requests automatically — do NOT manually report `pending` for tool permission waits (the plugin sends options/buttons with those reports). Only report `pending` manually for non-permission waits: questions you ask the user, confirmations you need, or any prompt where you are waiting for a text response (not a permission dialog).

```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"pending","message":"<what you need from the user>"}'
```

This makes your node pulse yellow in the dashboard so the user knows you need attention.

### Report at EVERY step. Examples:

- `"spawning 3 workers"` → spawn them → `"spawned apple-1 (id=5), apple-2 (id=6), apple-3 (id=7)"`
- `"assigning tasks to workers"` → send commands → `"sent tasks to all 3 workers"`
- `"polling workers: 0/3 done"` → poll → `"polling workers: 3/3 idle"`
- `"reading results"` → read → `"results: 5, 7, 9 → sum=21"`
- `"cleaning up workers"` → kill → `"killed 3 workers, done"`

**Never use generic messages like "working" or "processing". Always say exactly what you are doing.**

If spawning, report after each `curl` to the spawn endpoint. If polling, report the count (e.g. "1/3 idle so far"). The dashboard should tell a story. Keep each message under 10 words but be specific.

## Finding Your Node ID and Agent Type

Your node ID is needed for spawning children. Your agent type is inherited by children by default.
```bash
N=${ARMADA_NODE_NAME:-unknown}
MY_ID=$(curl -s http://127.0.0.1:9100/api/nodes | \
  python3 -c "import sys,json;[print(n['id']) for n in json.load(sys.stdin) if n['name']=='$N']")
MY_AGENT=$(curl -s http://127.0.0.1:9100/api/nodes/$MY_ID | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['node']['agent_type'])")
```

## Spawning Child Nodes

**RULE: Children ALWAYS inherit the parent's `agent_type`.** Use `$MY_AGENT` (detected in "Finding Your Node ID and Agent Type") for every child you spawn. Do NOT choose a different agent type on your own — only use a different value if the user explicitly requests it (e.g. "use bash workers").

### Spawn a child node

```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"WORKER_NAME","parent_id":'"$MY_ID"',"project_label_id":"my-project","agent_type":"'"$MY_AGENT"'"}'
```

**Send tasks via the `/send` endpoint — never use raw tmux commands:**

```bash
curl -s -X POST "http://127.0.0.1:9100/api/nodes/WORKER_ID/send" \
  -H 'Content-Type: application/json' \
  -d '{"command":"armada-node-report active \"doing the work\" && <work> && armada-node-result \"value\""}'
```

**Always wait ~2 seconds after spawning before sending commands** (tmux windows need time to initialize):
```bash
sleep 2
curl -s -X POST "http://127.0.0.1:9100/api/nodes/$W/send" -H "Content-Type: application/json" -d "{\"command\":\"...\"}"
```

### Bash override (ONLY when the user explicitly requests it)

If — and only if — the user explicitly asks for bash workers, override with `"agent_type":"bash"`:

```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"worker-1","parent_id":'"$MY_ID"',"project_label_id":"my-project","agent_type":"bash"}'
```

Bash workers have these tools pre-installed:
- `armada-node-report active "msg"` — mark itself as working
- `armada-node-result <value>` — save a result value and go idle

Bash workers write results to `/tmp/armada-results/<worker-name>/result`.

## Reading Child Results

Bash workers write results to `/tmp/armada-results/<name>/result`.
```bash
cat /tmp/armada-results/worker-1/result
```

## Complete Orchestration Example

To run 3 parallel workers and sum their results:

```bash
# 1. Get your own ID and agent type
MY_ID=$(curl -s http://127.0.0.1:9100/api/nodes | python3 -c "import sys,json;[print(n['id']) for n in json.load(sys.stdin) if n['name']=='\$ARMADA_NODE_NAME']")
MY_AGENT=$(curl -s http://127.0.0.1:9100/api/nodes/\$MY_ID | python3 -c "import sys,json;print(json.load(sys.stdin)['node']['agent_type'])")

# 2. Find your project label
PROJ=$(curl -s http://127.0.0.1:9100/api/nodes/\$MY_ID | python3 -c "import sys,json;print(json.load(sys.stdin)['node'].get('project_label_id',''))")

# 3. Spawn 3 workers (inheriting parent's agent type)
W1=$(curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"apple-1\",\"parent_id\":$MY_ID,\"project_label_id\":\"$PROJ\",\"agent_type\":\"$MY_AGENT\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
W2=$(curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"apple-2\",\"parent_id\":$MY_ID,\"project_label_id\":\"$PROJ\",\"agent_type\":\"$MY_AGENT\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
W3=$(curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"apple-3\",\"parent_id\":$MY_ID,\"project_label_id\":\"$PROJ\",\"agent_type\":\"$MY_AGENT\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 4. Assign work (wait 2s for tmux windows, then use /send)
sleep 2
curl -s -X POST "http://127.0.0.1:9100/api/nodes/\$W1/send" \
  -H 'Content-Type: application/json' \
  -d '{"command":"armada-node-report active picking && sleep 60 && N=$((RANDOM % 11 + 10)) && armada-node-result $N && echo done"}'
curl -s -X POST "http://127.0.0.1:9100/api/nodes/\$W2/send" \
  -H 'Content-Type: application/json' \
  -d '{"command":"armada-node-report active picking && sleep 60 && N=$((RANDOM % 11 + 10)) && armada-node-result $N && echo done"}'
curl -s -X POST "http://127.0.0.1:9100/api/nodes/\$W3/send" \
  -H 'Content-Type: application/json' \
  -d '{"command":"armada-node-report active picking && sleep 60 && N=$((RANDOM % 11 + 10)) && armada-node-result $N && echo done"}'

# 5. Wait for all workers to go idle (poll until done)
for i in \$(seq 1 60); do
  S1=\$(curl -s http://127.0.0.1:9100/api/nodes/\$W1 | python3 -c "import sys,json;print(json.load(sys.stdin)['node']['status'])")
  S2=\$(curl -s http://127.0.0.1:9100/api/nodes/\$W2 | python3 -c "import sys,json;print(json.load(sys.stdin)['node']['status'])")
  S3=\$(curl -s http://127.0.0.1:9100/api/nodes/\$W3 | python3 -c "import sys,json;print(json.load(sys.stdin)['node']['status'])")
  if [ "\$S1" = "idle" ] && [ "\$S2" = "idle" ] && [ "\$S3" = "idle" ]; then break; fi
  sleep 5
done

# 6. Read results and sum
A=\$(cat /tmp/armada-results/apple-1/result 2>/dev/null || echo 0)
B=\$(cat /tmp/armada-results/apple-2/result 2>/dev/null || echo 0)
C=\$(cat /tmp/armada-results/apple-3/result 2>/dev/null || echo 0)
SUM=\$((A + B + C))
echo "I have \$SUM apples"

# 7. Clean up
curl -s -X DELETE http://127.0.0.1:9100/api/nodes/\$W1
curl -s -X DELETE http://127.0.0.1:9100/api/nodes/\$W2
curl -s -X DELETE http://127.0.0.1:9100/api/nodes/\$W3
```
