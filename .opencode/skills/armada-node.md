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

To create a child worker node:
```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"worker-name","parent_id":PARENT_ID,"project_label_id":"my-project","agent_type":"opencode"}'
```

Replace `PARENT_ID` with your node ID. The child will auto-start with Armada skills loaded.

## Checking Children

```bash
curl -s http://127.0.0.1:9100/api/nodes/CHILD_ID
```

This returns the child's status, latest report, and activity log.

## Killing Children

```bash
curl -s -X DELETE http://127.0.0.1:9100/api/nodes/CHILD_ID
```

This kills the child and all its descendants.

## Guidelines

- Spawn children for parallel work (e.g., one child writes tests while another refactors)
- Check child status before assuming completion
- Kill children when their work is done to keep the tree clean
- Report your own status before and after every action
- If the Armada server is unreachable, continue working — the status will catch up
