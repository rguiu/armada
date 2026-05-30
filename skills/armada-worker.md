# Armada Worker Skill

A simplified skill for worker nodes that report status but don't spawn children. Use this for leaf nodes in the hierarchy that perform focused tasks.

Your node name comes from the `ARMADA_NODE_NAME` environment variable, set automatically when the node is created.

## Installation

Armada automatically copies this skill to `.opencode/skills/` or `.claude/skills/` when a node is created.

---

Your node name is available in `$ARMADA_NODE_NAME`. Use it in all status reports.

## Status Reporting

At the **start** of every response, run:
```bash
N=${ARMADA_NODE_NAME:-unknown}
MESSAGE="<5-word task summary>"
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

## Guidelines

- Focus on the task your parent node assigned you
- Report status clearly so the orchestrator can track your progress
- Complete your task and go idle — the orchestrator will kill your node when done
- Do not spawn children — you are a leaf node
- If the Armada server is unreachable, continue working
