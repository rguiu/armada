---
name: armada-worker
description: Deprecated — use armada-node instead. This skill redirects to the unified armada-node skill which handles both worker and orchestrator roles.
---

# Armada Worker — DEPRECATED

This skill has been merged into **armada-node**. All spawned nodes use the unified armada-node skill.

Use the `armada-node` skill instead. It covers:
- Worker behavior (do task, report result to parent)
- Sub-orchestrator behavior (spawn children, delegate, collect)
- Full MCP tools reference
- Messaging and polling patterns

## Quick Reference (Worker Mode)

If you are a leaf node with an assigned task:

```
report_status(status="active", message="starting task")
# ... do your work ...
my_info = get_my_info()
send_message(to_node_id=my_info["parent_id"], payload="done: <result>", msg_type="result")
report_status(status="idle", message="done, notified parent")
```

Then stop. Your parent will kill your node.
