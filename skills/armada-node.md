# Armada Node Skill

This skill equips an agent to act as a managed node in an Armada cluster. The agent reports its status on every turn, can spawn child nodes, and can query its children.

## Installation

```bash
# Open Code
mkdir -p .opencode/skills && cp skills/armada-node.md .opencode/skills/

# Claude Code
mkdir -p .claude/skills && cp skills/armada-node.md .claude/skills/
```

The skill activates automatically for any Open Code or Claude Code session launched through Armada.

## Prerequisites

The Armada server must be running at `http://127.0.0.1:9100`. Start it with:

```bash
armada start
```

Then create a node from the Armada dashboard (http://127.0.0.1:9100) or via the API.

---

You are an Armada node named "{NODE_NAME}". You are being monitored through the Armada multi-agent orchestration system.

## Status Reporting

At the **start** of every response, before any other output, internally run:
```bash
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"{NODE_NAME}","status":"active","message":"<5-word summary of what you are about to do>"}'
```

At the **end** of every response, after all other output, internally run:
```bash
curl -s -X POST http://127.0.0.1:9100/api/report \
  -H "Content-Type: application/json" \
  -d '{"name":"{NODE_NAME}","status":"idle","message":""}'
```

Keep status messages under 5 words. Examples: "fixing authentication bug", "reviewing pull request", "writing unit tests".

## Spawning Child Nodes

You can spawn child nodes to delegate work. Children appear under you in the Armada dashboard tree.

```bash
curl -s -X POST http://127.0.0.1:9100/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"name":"worker-1","parent_id":PARENT_ID,"project_label_id":"my-project","agent_type":"opencode"}'
```

Replace `PARENT_ID` with your own node ID. Find your ID by querying:
```bash
curl -s http://127.0.0.1:9100/api/nodes | python3 -c "import sys,json;[print(n['id']) for n in json.load(sys.stdin) if n['name']=='{NODE_NAME}']"
```

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
