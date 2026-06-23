---
name: armada-node
description: Use when ARMADA_NODE_NAME environment variable is set (running inside an Armada tmux window). This is the unified skill for ANY spawned Armada node — whether you are a worker doing a task or a sub-orchestrator coordinating children.
---

# Armada Node Skill

You are a node in an Armada cluster. Your role depends on your situation:

- **If you were spawned with a task** — you are a worker. Do the task, report the result to your parent, then go idle.
- **If you need to coordinate multiple subtasks** — you are a sub-orchestrator. Spawn children, delegate, collect results, report up.

Your node name is in `$ARMADA_NODE_NAME`. The Armada server runs at `http://127.0.0.1:9100`.

---

## Available MCP Tools (Complete Reference)

| Tool | Purpose |
|------|---------|
| `get_my_info` | Get your own node ID, name, agent_type, project, parent_id |
| `spawn_node` | Spawn a child node (inherits agent_type and project) |
| `send_task` | Send a command to a child node's terminal (auto-waits 2s) |
| `kill_node` | Kill a node and all its descendants |
| `get_tree` | Full node tree with status per node |
| `get_node` | Details + reports for one node |
| `list_nodes` | List all live nodes |
| `report_status` | Report your own status (active/idle/pending/error) |
| `list_projects` | List all project labels |
| `send_message` | Send a message to a specific node's inbox |
| `read_inbox` | Read your pending messages (or status="all" for everything) |
| `ack_message` | Mark a message as done |
| `broadcast` | Send a message to ALL your children |
| `post_to_queue` | Post a task to the shared work queue |
| `claim_from_queue` | Claim the next available task from the queue |

---

## Status Reporting — MANDATORY

**Report BEFORE and AFTER every significant action.** A silent node looks dead.

```
report_status(status="active", message="running test suite")
# ... do work ...
report_status(status="idle", message="tests passed, 42 assertions")
```

Statuses: `active` (working), `idle` (done/waiting), `pending` (need user input), `error` (failed).

Rules:
- Under 10 words per message
- Be specific: "parsing auth module" not "working"
- Report at EVERY step, not just start/end

For permission prompts (tool approvals), the Armada pending plugin handles it automatically — do NOT manually report `pending` for those. Only use `pending` for questions you ask the user.

---

## Getting Your Identity

```
my_info = get_my_info()
# Returns: {"id": 5, "name": "my-node", "parent_id": 2, "agent_type": "claude", "project_label_id": "..."}
```

Use `my_info["parent_id"]` to know who to report results to.

---

## As a Worker (Leaf Node)

If you were given a task, do this:

1. Report active
2. Do the work
3. Send result to parent
4. Report idle

```
report_status(status="active", message="starting assigned task")

# ... do your work ...

my_info = get_my_info()
send_message(to_node_id=my_info["parent_id"], payload="done: <your result summary>", msg_type="result")
report_status(status="idle", message="done, notified parent")
```

Then stop. Your parent will kill your node when it has collected all results.

---

## As a Sub-Orchestrator

If your task requires multiple parallel subtasks:

### Spawn children
```
spawn_node(name="subtask-1")  # inherits your agent_type and project
spawn_node(name="subtask-2")
```

### Send tasks (include your ID so children can message back)
```
my_info = get_my_info()
send_task(node_id=7, command="Do X. When done: send_message(to_node_id=<my_id>, payload='result: ...', msg_type='result')")
```

### Poll for results
`read_inbox()` is NOT blocking — you must call it repeatedly:

```
results = []
while len(results) < expected_count:
    report_status(status="active", message=f"waiting: {len(results)}/{expected_count} done")
    messages = read_inbox()
    for msg in messages:
        results.append(msg)
        ack_message(message_id=msg["id"])
```

### Clean up and report to YOUR parent
```
kill_node(node_id=7)
kill_node(node_id=8)
send_message(to_node_id=my_info["parent_id"], payload="all subtasks done: <summary>", msg_type="result")
report_status(status="idle", message="done, notified parent")
```

---

## Messaging Reference

### Send a message
```
send_message(to_node_id=5, payload="review complete: LGTM", msg_type="result")
```

### Read your inbox
```
read_inbox()                # pending messages only
read_inbox(status="all")    # all messages including done
```

### Acknowledge after processing
```
ack_message(message_id=42)
```

### Broadcast to all children
```
broadcast(payload="stop and report", msg_type="message")
```

### Work queue (for dynamic task distribution)
```
post_to_queue(payload="run integration tests")
claim_from_queue()  # returns next available task or empty
```

---

## Result Mechanism — Which to Use

| Mechanism | When to use |
|-----------|-------------|
| `send_message` (msg_type="result") | **Always.** This is the standard way to report results. |
| `/tmp/armada-results/<name>/result` | Legacy, bash-only nodes that use `armada-node-result`. Do not use for AI agent nodes. |

---

## Guidelines

- Always use MCP tools (not curl) when available
- Kill children when done — keep the tree clean
- If Armada server is unreachable, continue working on your task
- Check the dashboard at http://127.0.0.1:9100 to visualize the tree
- Children inherit agent_type and project — only override if explicitly requested
