---
name: armada-worker
description: Use ONLY when ARMADA_NODE_NAME environment variable is set and you are a LEAF node (should NOT spawn children). This skill teaches mandatory status reporting via the Armada MCP tools on EVERY turn. Triggers on: armada worker, ARMADA_NODE_NAME, leaf node, report status.
---

# Armada Worker Skill

A simplified skill for worker nodes that report status but don't spawn children. Use this for leaf nodes in the hierarchy that perform focused tasks.

Your node name comes from the `ARMADA_NODE_NAME` environment variable, set automatically when the node is created.

## Installation

Armada automatically copies this skill to `.opencode/skills/` or `.claude/skills/` when a node is created.

---

Your node name is available in `$ARMADA_NODE_NAME`. The Armada MCP tools handle identity automatically.

## Status Reporting — MANDATORY

**You MUST report status BEFORE and AFTER every significant action** using the `report_status` MCP tool.

Before any action (mark yourself active):
```
report_status(status="active", message="<what you are about to do>")
```

After completing the action (mark yourself idle with what you did):
```
report_status(status="idle", message="<what you just completed>")
```

Be specific. Good messages: "reading config file", "running tests", "generating report". Bad: "working".

## Notify Parent on Completion — MANDATORY

**When you finish your assigned task, send a completion message to your parent node.**

```
my_info = get_my_info()
send_message(to_node_id=my_info.parent_id, payload="job completed: <summary of what you did>", msg_type="result")
report_status(status="idle", message="done, notified parent")
```

This lets the orchestrator know you're done without polling.

## Guidelines

- Focus on the task your parent node assigned you
- Report status clearly so the orchestrator can track your progress
- Complete your task and go idle — the orchestrator will kill your node when done
- Do not spawn children — you are a leaf node
- If the Armada server is unreachable, continue working
