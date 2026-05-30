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

## Status Reporting

At the **start** of every response, before any other output, run:
```bash
N=${ARMADA_NODE_NAME:-unknown}
MESSAGE="<5-word task description>"
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"active","message":"'"$MESSAGE"'"}'
```

At the **end** of every response, run:
```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$N"'","status":"idle","message":""}'
```

Keep status messages under 5 words. Examples: "fixing authentication bug", "reviewing pull request", "writing unit tests".

## Finding Your Node ID

Your node ID is needed for spawning children:
```bash
N=${ARMADA_NODE_NAME:-unknown}
curl -s http://127.0.0.1:9100/api/nodes | \
  python3 -c "import sys,json;[print(n['id']) for n in json.load(sys.stdin) if n['name']=='$N']"
```

## Spawning Child Nodes

### AI agent children (opencode / claude)

To create a child that runs its own AI agent:
```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"worker-name","parent_id":PARENT_ID,"project_label_id":"my-project","agent_type":"opencode"}'
```

The child auto-starts with Armada skills loaded. Attach to it and give it a task.

### Bash worker children (for parallel computation)

To create a bash worker that runs a shell command and reports its result:
```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"worker-1","parent_id":PARENT_ID,"project_label_id":"my-project","agent_type":"bash"}'
```

Then send it a command via tmux. The worker has these tools pre-installed:
- `armada-node-report active "msg"` — mark itself as working
- `armada-node-result <value>` — save a result value and go idle

Example — send a computation to the worker:
```bash
tmux send-keys -t "armada:worker-1" "armada-node-report active 'computing' && sleep 60 && N=\$RANDOM && armada-node-result \$N && echo done" Enter
```

The worker will:
1. Report status "active: computing"
2. Wait (sleep)
3. Write its result to `/tmp/armada-results/worker-1/result`
4. Report status "idle"

## Reading Child Results

Bash workers write results to `/tmp/armada-results/<name>/result`.
```bash
cat /tmp/armada-results/worker-1/result
```

## Complete Orchestration Example

To run 3 parallel workers and sum their results:

```bash
# 1. Get your own ID
MY_ID=$(curl -s http://127.0.0.1:9100/api/nodes | python3 -c "import sys,json;[print(n['id']) for n in json.load(sys.stdin) if n['name']=='\$ARMADA_NODE_NAME']")

# 2. Find your project label
PROJ=$(curl -s http://127.0.0.1:9100/api/nodes/\$MY_ID | python3 -c "import sys,json;print(json.load(sys.stdin)['node'].get('project_label_id',''))")

# 3. Spawn 3 workers
W1=$(curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"apple-1\",\"parent_id\":$MY_ID,\"project_label_id\":\"$PROJ\",\"agent_type\":\"bash\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
W2=$(curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"apple-2\",\"parent_id\":$MY_ID,\"project_label_id\":\"$PROJ\",\"agent_type\":\"bash\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
W3=$(curl -s -X POST http://127.0.0.1:9100/api/nodes -H "Content-Type: application/json" -d "{\"name\":\"apple-3\",\"parent_id\":$MY_ID,\"project_label_id\":\"$PROJ\",\"agent_type\":\"bash\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 4. Assign work (after a short delay for tmux windows to be ready)
sleep 2
tmux send-keys -t "armada:apple-1" 'armada-node-report active "picking apples" && sleep 60 && N=$((RANDOM % 11 + 10)) && armada-node-result $N && echo done' Enter
tmux send-keys -t "armada:apple-2" 'armada-node-report active "picking apples" && sleep 60 && N=$((RANDOM % 11 + 10)) && armada-node-result $N && echo done' Enter
tmux send-keys -t "armada:apple-3" 'armada-node-report active "picking apples" && sleep 60 && N=$((RANDOM % 11 + 10)) && armada-node-result $N && echo done' Enter

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
